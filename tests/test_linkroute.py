"""Segment-wise route matching: a literal client segment matches a server param, literal beats param."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (puts the package on sys.path)
from test_link_store import edge

from cdp.link import scan_links


def _snap(repo, edges):
    return {"repo": repo, "head": "h", "dataflow": {"edges": edges}}


def links(calls, routes):
    c = [edge("c%d" % i, "http:" + t, "http_out", "c%d.cs" % i) for i, t in enumerate(calls)]
    r = [edge("r%d" % i, "route:" + t, "http_in", "r%d.java" % i) for i, t in enumerate(routes)]
    rep = scan_links([_snap("web", c), _snap("api", r)])
    return [(l["caller"]["node"], l["callee"]["node"], l["match_kind"]) for l in rep["links"]]


class LiteralToParamTest(unittest.TestCase):
    def test_literal_segment_matches_param_as_heuristic(self):
        for call, route in [("GET /users/me", "GET /users/{id}"),
                            ("GET /orders/123/items", "GET /orders/{id}/items"),
                            ("GET /v1/reservations/active", "GET /v1/reservations/{id}")]:
            self.assertEqual([("c0", "r0", "heuristic")], links([call], [route]), call)

    def test_client_param_matches_server_literal(self):
        self.assertEqual([("c0", "r0", "heuristic")], links(["GET /users/{x}"], ["GET /users/me"]))

    def test_literal_route_beats_param_route(self):
        self.assertEqual([("c0", "r1", "exact")],
                         links(["GET /users/me"], ["GET /users/{id}", "GET /users/me"]))

    def test_param_routes_alone_still_all_match(self):
        self.assertEqual(2, len(links(["GET /users/me"], ["GET /users/{id}", "GET /users/<name>"])))

    def test_different_verbs_never_match(self):
        self.assertEqual([], links(["POST /users/me"], ["GET /users/{id}"]))

    def test_param_match_needs_a_shared_informative_segment(self):
        self.assertEqual([], links(["GET /a/b"], ["GET /{x}/{y}"]))
        self.assertEqual([], links(["GET /v1/foo"], ["GET /v1/{x}"]))

    def test_segment_count_must_agree(self):
        self.assertEqual([], links(["GET /users/me/extra"], ["GET /users/{id}"]))

    def test_context_prefix_suffix_rule_still_applies_with_params(self):
        self.assertEqual([("c0", "r0", "heuristic")],
                         links(["GET /sql-pool/v1/reservations/active"],
                               ["GET /unified-store/sql-pool/v1/reservations/{id}"]))

    def test_suffix_match_never_lets_a_param_stand_in_at_the_prefix_boundary(self):
        self.assertEqual([], links(["POST /{t}/card/{e}/artifact/bulk"], ["POST /{t}/Card/{e}/bulk"]))
        self.assertEqual([], links(["POST /v1/{t}/access/securable/read"],
                                   ["POST /v2/{t}/catalog/Access/securable/read"]))
        self.assertEqual([], links(["DELETE /admin/{t}/securables/{s}/entities"],
                                   ["DELETE /v1/Admin/meta/{t}/sql-instances/{i}"]))


if __name__ == "__main__":
    unittest.main()
