import unittest

from cdp.entail import ENTAILED, CONSISTENT, CONTRADICTED, entail_claims, summarize
from cdp.state import fold


def _claim(**kwargs):
    base = {
        "id": "c.one",
        "kind": "side_effect",
        "subject": "com.example.Server",
        "statement": "persists a server entity to the database",
        "evidence": [],
        "confidence": "high",
    }
    base.update(kwargs)
    return base


class EntailClaimsTest(unittest.TestCase):
    def test_matching_io_edge_is_entailed(self):
        extraction = {"io_edges": [{"source": "com.example.Server", "channel": "persist", "target": "table:servers"}],
                      "defines": []}
        claim = _claim(channel="persist")
        out = entail_claims([claim], extraction)
        self.assertEqual(out[0]["verdict"], ENTAILED)

    def test_no_structural_counterpart_is_consistent(self):
        extraction = {"io_edges": [], "defines": []}
        claim = _claim(channel="persist")
        out = entail_claims([claim], extraction)
        self.assertEqual(out[0]["verdict"], CONSISTENT)

    def test_visibility_mismatch_is_contradicted(self):
        extraction = {"io_edges": [], "defines": [
            {"fqn": "com.example.Server", "kind": "class", "visibility": "private",
             "anchor": {"file": "a.java", "line": 1, "anchor": "class Server {}"}}
        ]}
        claim = _claim(visibility="public")
        out = entail_claims([claim], extraction)
        self.assertEqual(out[0]["verdict"], CONTRADICTED)

    def test_human_claim_contradicted_becomes_contested(self):
        """R11 (Phase 4, M4.4): a human claim contradicted by extraction is
        `contested`, not silently accepted -- confidence is downgraded even
        though the verdict itself stays `contradicted` (the structural fact)."""
        extraction = {"io_edges": [], "defines": [
            {"fqn": "com.example.Server", "kind": "class", "visibility": "private",
             "anchor": {"file": "a.java", "line": 1, "anchor": "class Server {}"}}
        ]}
        claim = _claim(visibility="public", author_kind="human", confidence="high")
        out = entail_claims([claim], extraction)
        self.assertEqual(out[0]["verdict"], CONTRADICTED)
        self.assertEqual(out[0]["confidence"], "contested")

    def test_llm_claim_contradicted_keeps_its_own_confidence(self):
        """R11 only downgrades a *human* claim -- an agent's contradicted
        claim is gold for the reflection loop (Phase 9), not "contested"."""
        extraction = {"io_edges": [], "defines": [
            {"fqn": "com.example.Server", "kind": "class", "visibility": "private",
             "anchor": {"file": "a.java", "line": 1, "anchor": "class Server {}"}}
        ]}
        claim = _claim(visibility="public", confidence="high")
        out = entail_claims([claim], extraction)
        self.assertEqual(out[0]["verdict"], CONTRADICTED)
        self.assertEqual(out[0]["confidence"], "high")

    def test_matching_visibility_is_not_contradicted(self):
        extraction = {"io_edges": [], "defines": [
            {"fqn": "com.example.Server", "kind": "class", "visibility": "public",
             "anchor": {"file": "a.java", "line": 1, "anchor": "class Server {}"}}
        ]}
        claim = _claim(visibility="public")
        out = entail_claims([claim], extraction)
        self.assertEqual(out[0]["verdict"], CONSISTENT)

    def test_no_statement_text_matching(self):
        """Matching is over subject+channel, never the statement wording --
        a claim paraphrasing an edge in unrelated words still entails."""
        extraction = {"io_edges": [{"source": "com.example.Server", "channel": "persist", "target": "table:servers"}],
                      "defines": []}
        claim = _claim(channel="persist", statement="something totally unrelated in wording")
        out = entail_claims([claim], extraction)
        self.assertEqual(out[0]["verdict"], ENTAILED)

    def test_missing_extraction_defaults_consistent(self):
        out = entail_claims([_claim(channel="persist")], None)
        self.assertEqual(out[0]["verdict"], CONSISTENT)


class SummarizeTest(unittest.TestCase):
    def test_counts_and_per_node_ratio(self):
        claims = [
            {"verdict": ENTAILED, "source_node": "root/a"},
            {"verdict": ENTAILED, "source_node": "root/a"},
            {"verdict": CONSISTENT, "source_node": "root/a"},
            {"verdict": CONTRADICTED, "source_node": "root/b"},
        ]
        summary = summarize(claims)
        self.assertEqual(summary["counts"], {ENTAILED: 2, CONSISTENT: 1, CONTRADICTED: 1})
        self.assertEqual(summary["rate_contradicted"], 0.25)
        self.assertAlmostEqual(summary["by_node"]["root/a"]["entailed_ratio"], round(2 / 3, 4))
        self.assertEqual(summary["by_node"]["root/b"]["entailed_ratio"], 0.0)


class FoldEntailmentIntegrationTest(unittest.TestCase):
    def test_fold_assigns_verdict_and_never_drops_contradicted(self):
        xref = {"symbols": {}}
        extraction = {
            "io_edges": [{"source": "com.example.Server", "channel": "persist", "target": "table:servers"}],
            "defines": [{"fqn": "com.example.Server", "kind": "class", "visibility": "private",
                         "anchor": {"file": "a.java", "line": 1, "anchor": "class Server {}"}}],
        }
        patch = {
            "schema_version": "1.0.0", "node": "root", "run_id": "cdp-abc123456789",
            "status": "complete", "author_kind": "python",
            "claims": [
                _claim(id="c.one", channel="persist"),
                _claim(id="c.two", subject="com.example.Server", kind="visibility",
                       statement="Server is publicly exposed as an entrypoint",
                       visibility="public"),
            ],
        }
        result = fold([patch], xref, extraction=extraction)
        verdicts = {c["id"]: c["verdict"] for c in result["claims"]}
        self.assertEqual(verdicts["c.one"], ENTAILED)
        self.assertEqual(verdicts["c.two"], CONTRADICTED)
        self.assertEqual(len(result["contradictions"]), 1)
        self.assertEqual(result["contradictions"][0]["id"], "c.two")
        # Contradicted claims are logged, not dropped from claims[].
        self.assertIn("c.two", verdicts)
        self.assertEqual(result["entailment"]["counts"][CONTRADICTED], 1)


if __name__ == "__main__":
    unittest.main()
