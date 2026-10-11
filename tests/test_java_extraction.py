"""Java extraction regressions (B1-B4, B6-B8, B12), on `tests/fixtures/javarepo`.

Each of these failed on the line-regex extractor: it indexed only `public|protected|private`
methods that carried their modifier on the name's line, recorded no constructors or
interface methods, and resolved only calls on a variable declared in the same file.
`scripts/java_benchmark.py` measures the same things against javac's own trees.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, Pipeline, make_repo

sys.path.insert(0, str(SKILL_ROOT / "scripts"))

PKG = "com.acme.pool."
SVC = PKG + "service.ServerService"
HELPER = PKG + "service.HelperService"
SERVER = PKG + "model.Server"
REPO = PKG + "repo.ServerRepository"


class _Store:
    """Just enough of a query Store for `q_symbol`."""

    def __init__(self, p: Pipeline) -> None:
        self.extraction, self.xref, self.inventory = p.extraction, p.xref, p.inventory
        self.state = {"claims": [], "unknowns": [], "provenance": {}}


class JavaExtractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(make_repo(Path(cls.tmp.name), "javarepo"))
        cls.symbols = cls.p.xref["symbols"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def callers(self, fqn):
        return sorted((u["file"].rsplit("/", 1)[-1], u["anchor"]["line"])
                      for u in self.p.xref["used_by"].get(fqn, []))

    def test_b3_package_private_methods_and_junit5_tests_are_indexed(self):
        self.assertEqual(self.symbols[SERVER + "#weight"]["visibility"], "package")
        self.assertIn(PKG + "service.ServerServiceTest#registersAServer", self.symbols)
        self.assertEqual(self.symbols[HELPER + "#normalise"]["visibility"], "package")

    def test_b6_interface_methods_are_indexed(self):
        self.assertEqual(self.symbols[PKG + "service.Provisioner#getPriority"]["kind"], "method")
        self.assertIn(PKG + "service.Provisioner#label", self.symbols)

    def test_b7_constructors_are_indexed_as_init(self):
        self.assertIn(SERVER + "#<init>", self.symbols)
        self.assertIn(SVC + "#<init>", self.symbols)
        # `new Server(name)` and `this("anon")` are calls to it
        files = {f for f, _ in self.callers(SERVER + "#<init>")}
        self.assertEqual(files, {"ServerRepository.java", "HelperService.java", "Server.java"})

    def test_b4_non_final_static_and_instance_fields_are_indexed(self):
        self.assertEqual(self.symbols[SERVER + ".MAX_MAINTENANCE_MINUTES"]["kind"], "field")
        self.assertEqual(self.symbols[SERVER + ".DEFAULT_NAME"]["kind"], "constant")
        self.assertIn(SVC + ".repo", self.symbols)

    def test_b1_calls_to_inherited_methods_are_recorded_on_the_declaring_class(self):
        sites = self.callers(HELPER + "#getServersForStaticPool")
        self.assertEqual([f for f, _ in sites], ["ServerService.java"] * 2)
        self.assertNotIn(SVC + "#getServersForStaticPool", self.p.xref["used_by"])

    def test_b8_chained_static_method_reference_and_field_calls(self):
        get_name = {f for f, _ in self.callers(SERVER + "#getName")}
        self.assertIn("ServerService.java", get_name)            # repo.find(name).getName()
        self.assertEqual(len(self.callers(SERVER + "#withHint")), 2)  # chained, and in HelperService
        self.assertIn("ServerService.java", {f for f, _ in self.callers(HELPER + "#normalise")})  # static
        find = self.callers(REPO + "#find")
        self.assertGreaterEqual(len(find), 4)  # field-typed, `repo::find`, in findAll, in touch
        self.assertIn(("ServerService.java", 39), find)  # `names.stream().map(repo::find)`
        # the test's `service.register(...)` through a local typed in the same file
        self.assertIn("ServerServiceTest.java", {f for f, _ in self.callers(SVC + "#register")})

    def test_b2_class_method_lookup_is_exact_and_follows_inheritance(self):
        from cdp.query.lookup import q_symbol
        store = _Store(self.p)
        hit = q_symbol(store, "ServerService#setServerHint")["found"]
        self.assertEqual([h["fqn"] for h in hit], [HELPER + "#setServerHint"])
        self.assertIn("inherits it from", hit[0]["via"])
        self.assertEqual(hit[0]["used_by_count"], 1)
        self.assertEqual(q_symbol(store, "ServerService#setServerHin")["found"], [])  # never a prefix
        ctor = q_symbol(store, "ServerService#ServerService")["found"]
        self.assertEqual([h["fqn"] for h in ctor], [SVC + "#<init>"])

    def test_b12_flyway_placeholders_and_comments(self):
        tables = {e["target"] for e in self.p.extraction["io_edges"] if e["target"].startswith("table:")}
        self.assertEqual(tables, {"table:QRTZ_LOCKS", "table:server"})

    def test_python_prose_is_not_a_table(self):
        from cdp.lang import extract_file

        def tables(src):
            facts = extract_file("m.py", src.splitlines(), "m")
            return sorted(e["target"] for e in facts.io_edges if e["target"].startswith("table:"))

        self.assertEqual(tables('def f():\n    """update body of the request; select a from the list"""\n'), [])
        self.assertEqual(tables("def f():\n    print('update failed')  # select x from the pile\n"), [])
        self.assertEqual(tables('def f(cur):\n    cur.execute("UPDATE users SET a = 1")\n'), ["table:users"])
        self.assertEqual(tables('def f(cur):\n    cur.execute("SELECT * FROM foo")\n'), ["table:foo"])


@unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "needs a JDK")
class JavaBenchmarkTest(unittest.TestCase):
    """The index against javac's trees on the fixture: the FIXPLAN P5 targets
    (methods >= 99%, call sites >= 90%) must hold on a repo that has every
    construct, not just on the real one."""

    def test_fixture_meets_the_targets(self):
        import java_benchmark
        repo = java_benchmark.as_git_repo(SKILL_ROOT / "tests" / "fixtures" / "javarepo")
        truth = java_benchmark.run_truth(SKILL_ROOT / "tests" / "fixtures" / "javarepo", None, "")
        out = java_benchmark.measure(repo, truth, 5)
        self.assertGreaterEqual(out["methods"][2], 99, out["methods_missed_sample"])
        self.assertGreaterEqual(out["fields"][2], 99, out["fields_missed_sample"])
        self.assertGreaterEqual(out["calls"][2], 90, out["calls_missed_sample"])
        self.assertGreaterEqual(out["calls_precision"][2], 95, out["calls_extra_sample"])
        self.assertGreater(out["config"][1], 5)  # the fixture really has config reads
        self.assertGreaterEqual(out["config"][2], 90, out["config_missed_sample"])
        self.assertGreaterEqual(out["config_precision"][2], 95, out["config_extra_sample"])


if __name__ == "__main__":
    unittest.main()
