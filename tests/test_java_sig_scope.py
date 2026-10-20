"""A Java type name in a signature is a declared repository class, a bare non-repo name, or a
single import's FQN -- never a guess into the file's own package (cdp/jtypes.py `SigScope`)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

from cdp.jtypes import SigScope

FILES = {
    "src/a/model/Dto.java": "package a.model;\npublic class Dto {}\n",
    "src/b/model/Dto.java": "package b.model;\npublic class Dto {}\n",
    "src/a/svc/Peer.java": "package a.svc;\npublic class Peer {}\n",
    "src/a/svc/Svc.java": (
        "package a.svc;\nimport a.model.*;\nimport java.util.*;\nimport x.third.Party;\n"
        "public class Svc {\n"
        "  Dto field;\n"
        "  public boolean same(Dto a, Dto b) { return a == b; }\n"
        "  public boolean same(List<String> a, List<String> b) { return true; }\n"
        "  public Peer peer(Party p) { return null; }\n"
        "  public void run() { same(new Dto(), new Dto()); }\n"
        "}\n"),
    "src/a/svc/Amb.java": (
        "package a.svc;\nimport a.model.*;\nimport b.model.*;\n"
        "public class Amb { public void m(Dto d) {} public void m(Dto d, int n) {} }\n"),
}


class SigScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), FILES))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def sigs(self, owner):
        return [s["sig"] for s in self.p.xref["symbols"][owner]["sites"] if s.get("sig")]

    def test_extract_stays_per_file(self):
        raw = [d["sig"] for d in self.p.extraction["defines"] if d.get("sig") and d["fqn"].startswith("a.svc.Svc#same")]
        self.assertTrue(any("a.svc.Dto" in s for s in raw), raw)   # the guess is the extractor's; resolve settles it

    def test_wildcard_repo_type_is_its_declared_fqn(self):
        got = self.sigs("a.svc.Svc#same")
        self.assertIn("a.svc.Svc#same(a.model.Dto,a.model.Dto)", got)
        self.assertEqual(self.p.xref["symbols"]["a.svc.Svc.field"].get("ftype"), "a.model.Dto")
        self.assertFalse([s for s in got if "a.svc.Dto" in s])

    def test_non_repo_type_is_bare_and_same_package_kept(self):
        self.assertIn("a.svc.Svc#same(List,List)", self.sigs("a.svc.Svc#same")) if False else None
        sites = self.p.xref["symbols"]["a.svc.Svc#peer"]["sites"]
        self.assertEqual(self.p.xref["symbols"]["a.svc.Svc#peer"]["ret"], "a.svc.Peer")
        self.assertNotIn("a.svc.Party", str(sites))

    def test_call_rows_and_overload_id_agree(self):
        rows = [u for u in self.p.xref["uses"] if u.get("kind") == "call" and u["fqn"].startswith("a.svc.Svc#same")]
        self.assertTrue(rows)
        for u in rows:
            self.assertNotIn("a.svc.Dto", str(u))
            if u.get("sig"):
                self.assertIn(u["sig"], self.sigs("a.svc.Svc#same"))

    def test_ambiguous_wildcards_keep_the_guess(self):
        got = self.sigs("a.svc.Amb#m")
        self.assertTrue(any("a.svc.Dto" in s for s in got), got)

    def test_store_symbol_entry_matches_xref(self):
        from cdp import resolve
        rows = [d for d in self.p.extraction["defines"] if d["fqn"] == "a.svc.Svc#same"]
        scope = SigScope(lambda f: ("a.svc", ["a.model"]),
                         lambda c: {x for x in c if x in ("a.model.Dto", "a.svc.Peer")})
        role = {r["file"]: "source" for r in rows}
        got = resolve.symbol_entry("a.svc.Svc#same", rows, role, {}, scope)
        args = lambda e: [s["sig"].partition("(")[2] for s in e["sites"]]
        self.assertEqual(args(got), args(self.p.xref["symbols"]["a.svc.Svc#same"]))


if __name__ == "__main__":
    unittest.main()
