"""H5/H6/H7/I4/L13/E8/B18: one validation layer, short shas, no tracebacks, no phantom stores.

Unit tests cover the shared helpers; `CliSweepTest` drives the real CLI on a scanned temp repo
with bad inputs and asserts the contract: a nonzero rc, a message, never a traceback."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

import repo_layouts as L
from repo_layouts import Cdp
from cdp import rollback as rollback_mod
from cdp.parser import build_parser
from cdp.util import (LIMITS, ArgError, CdpError, check_int, check_limit, positive_int, resolve_prefix)

SRC = "src/main/java/com/example/svc/"
CLAIM = {"id": "c.1", "kind": "naming", "subject": "com.example.svc.Child", "confidence": "high",
         "statement": "Child extends Base.",
         "evidence": [{"file": SRC + "Child.java", "line": 5,
                       "anchor": "public class Child extends Base implements Provisioner {"}]}


class HelpersTest(unittest.TestCase):
    def test_check_int_rejects_wrong_types_and_ranges(self):
        self.assertEqual(check_int(3, "n", 1), 3)
        self.assertEqual(check_int("3", "n", 1), 3)  # a command line is text
        for bad in ("ten", True, 1.5, None, [1]):
            with self.assertRaises(ArgError):
                check_int(bad, "n", 0)
        with self.assertRaises(ArgError):
            check_int(0, "n", 1)
        with self.assertRaises(ArgError):
            check_int("2", "n", 0, strict=True)  # a typed (MCP) argument is not text

    def test_argparse_types_give_usage_errors_not_tracebacks(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")
        self.assertEqual(positive_int("4"), 4)

    def test_resolve_prefix_unique_ambiguous_unknown(self):
        known = ["ab12cd34" + "0" * 32, "ab12ef56" + "0" * 32, "9f" + "0" * 38, "9f" + "0" * 38 + "+dirty:t"]
        self.assertEqual(resolve_prefix("ab12cd", known), known[0])
        self.assertEqual(resolve_prefix(known[1], known), known[1])
        self.assertEqual(resolve_prefix("9f00", known), known[2])  # the clean commit beats its dirty snapshot
        with self.assertRaises(CdpError) as amb:
            resolve_prefix("ab12", known)
        self.assertIn("ambiguous", str(amb.exception))
        self.assertIn("ab12cd34", str(amb.exception))
        self.assertIn("ab12ef56", str(amb.exception))
        for bad in ("dead", "xyz", "ab"):
            with self.assertRaises(CdpError) as unk:
                resolve_prefix(bad, known)
            self.assertIn("ab12cd34", str(unk.exception))  # candidates are listed

    def test_run_id_resolution_uses_the_log(self):
        log = [{"run_id": "cdp-aaaa11112222"}, {"run_id": "cdp-aaaa99998888"}, {"run_id": "cdp-bbbb00001111"}]
        self.assertEqual(rollback_mod.resolve_run_id("bbbb", log), "cdp-bbbb00001111")
        self.assertEqual(rollback_mod.resolve_run_id("bbbb00001111ffff0000", log), "cdp-bbbb00001111")
        self.assertEqual(rollback_mod.resolve_run_id("cdp-bbbb0", log), "cdp-bbbb00001111")
        with self.assertRaises(CdpError):
            rollback_mod.resolve_run_id("aaaa", log)


def _parse(*argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), self_assert_exit():
        build_parser().parse_args(list(argv))
    return err.getvalue()


@contextlib.contextmanager
def self_assert_exit():
    try:
        yield
    except SystemExit as exc:
        if exc.code != 2:
            raise AssertionError("exit code %r, expected 2" % (exc.code,))
    else:
        raise AssertionError("accepted")


class ParserRangesTest(unittest.TestCase):
    BAD = [
        ("scan", "--max-concurrent", "0"), ("scan", "--max-concurrent", "-2"), ("scan", "--workers", "-3"),
        ("scan", "--workers", "0"), ("scan", "--max-hops", "-1"), ("scan", "--max-leaf-files", "0"),
        ("scan", "--max-leaf-loc", "0"), ("scan", "--max-hops", "x"),
        ("query", "stats", "--budget", "-5"), ("query", "trace", "A", "--max-hops", "-1"),
        ("run", "--wave", "0", "--parallel", "0"), ("run", "--wave", "0", "--max-attempts", "0"),
        ("run", "--wave", "0", "--timeout", "-1"), ("run", "--wave", "0", "--timeout", "0"),
        ("run", "--wave", "-1"), ("run", "--wave", "0", "--lessons", "0"),
        ("prompts", "--wave", "-1"), ("prompts", "--lessons", "-3"),
        ("compact", "--keep-generations", "0"), ("compact", "--keep-generations", "-1"),
        ("compact", "--compact-threshold", "5"), ("compact", "--compact-threshold", "-0.1"),
        ("reflect", "--runner-cmd", "x", "--limit", "0"), ("reflect", "--runner-cmd", "x", "--timeout", "-1"),
        ("doctor", "--model", "m", "--runner-cmd", "x", "--timeout", "0"),
        ("lessons", "show", "--version", "0"), ("holdout", "--lessons", "0"),
        ("link", "run", "--timeout", "0"), ("link", "run", "--max-attempts", "0"),
        ("selftest", "--min-tests", "-1"),
    ]

    def test_every_bad_value_is_a_usage_error(self):
        for argv in self.BAD:
            with self.subTest(argv=" ".join(argv)):
                self.assertTrue(_parse(*argv).strip(), "no message")

    def test_good_boundary_values_parse(self):
        ns = build_parser().parse_args(["scan", "--max-concurrent", "1", "--max-hops", "0", "--workers", "1"])
        self.assertEqual((ns.max_concurrent, ns.max_hops, ns.workers), (1, 0, 1))
        build_parser().parse_args(["query", "stats", "--budget", "0"])

    def test_cli_flags_and_mcp_limits_agree(self):
        flags = {"budget": ("query", "stats", "--budget"), "offset": ("query", "stats", "--offset"),
                 "max_tokens": ("query", "stats", "--max-tokens"), "max_hops": ("scan", "--max-hops"),
                 "max_leaf_files": ("scan", "--max-leaf-files"), "max_leaf_loc": ("scan", "--max-leaf-loc"),
                 "max_concurrent": ("scan", "--max-concurrent"), "workers": ("scan", "--workers")}
        self.assertEqual(set(flags), set(LIMITS))
        for name, argv in flags.items():
            lo, _hi = LIMITS[name]
            build_parser().parse_args(list(argv) + [str(lo)])
            with self.subTest(name=name):
                _parse(*argv, str(lo - 1))
                with self.assertRaises(ArgError):
                    check_limit(name, lo - 1)

    def test_mcp_schema_minimums_match_limits(self):
        from mcp_server.schemas import TOOL_SCHEMAS
        for tool in ("cdp_query", "cdp_scan"):
            for name, prop in TOOL_SCHEMAS[tool]["inputSchema"]["properties"].items():
                if name in LIMITS and prop.get("type") == "integer":
                    self.assertEqual(prop.get("minimum"), LIMITS[name][0], "%s.%s" % (tool, name))


@L.needs_git
class McpArgumentsTest(unittest.TestCase):
    """A direct tool call (no schema in front of it) fails cleanly, and the server answers -32602."""

    def test_tools_validate_at_runtime(self):
        from mcp_server import tools
        for kw in ({"max_hops": "2"}, {"budget": "ten"}, {"budget": True}, {"budget": -1}, {"exact": "yes"},
                   {"exclude_role": "test"}, {"term": 5}):
            with self.subTest(kw=kw), self.assertRaises(ArgError):
                tools.cdp_query("/nonexistent", "symbol", **kw)
        for kw in ({"max_concurrent": 0}, {"workers": "3"}, {"max_hops": -1}, {"max_leaf_files": 0}):
            with self.subTest(kw=kw), self.assertRaises(ArgError):
                tools.cdp_scan("/nonexistent", **kw)

    def test_server_reports_invalid_params(self):
        from mcp_server import server, tools
        real = tools.TOOLS["cdp_query"]
        tools.TOOLS["cdp_query"] = lambda **kw: tools.cdp_query(**dict(kw, max_hops="2"))
        try:  # the schema passes (budget absent); the runtime check must still answer -32602
            reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "cdp_query", "arguments": {"repo": "/x", "kind": "trace"}}})
        finally:
            tools.TOOLS["cdp_query"] = real
        self.assertEqual(reply["error"]["code"], -32602)
        self.assertIn("max_hops", reply["error"]["message"])
        self.assertNotIn("Error:", reply["error"]["message"])


@L.needs_git
class CliSweepTest(unittest.TestCase):
    """The real CLI on a scanned two-commit repo."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.repo = L.java_inheritance(cls.tmp)
        cls.cdp = Cdp(cls.tmp, cls.repo.path)
        cls.c1 = cls.repo.head()
        cls.cdp.scan()
        cls.cdp.inject_model_patch("root", [dict(CLAIM)])
        cls.repo.write(SRC + "Base.java", cls.repo.read(SRC + "Base.java").replace("return 1;", "return 11;"))
        cls.c2 = cls.repo.commit("two")
        cls.cdp.refresh()
        (cls.tmp / "bad.json").write_text("{bad")
        (cls.tmp / "arr.json").write_text("[1, 2]")
        (cls.tmp / "afile").write_text("x")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_cdp(self, *args):
        args = [a.replace("TMP", str(self.tmp)) for a in args]
        if args[0] == "link":  # location flags go before `link`: its subparsers do not take them
            import os, subprocess, sys
            cmd = [sys.executable, str(L.RUN_PY), "--repo", str(self.cdp.target), "--state-dir", str(self.cdp.home)]
            return subprocess.run(cmd + args, capture_output=True, text=True,
                                  env=dict(os.environ, CDP_HOME=str(self.cdp.home)))
        return self.cdp.run(*args, check=False)

    def assertFails(self, *args, contains=None):
        p = self.run_cdp(*args)
        self.assertNotIn("Traceback", p.stderr, " ".join(args))
        self.assertNotEqual(p.returncode, 0, "%s -> rc 0\n%s" % (" ".join(args), p.stdout[-300:]))
        self.assertTrue(p.stderr.strip(), "no message: " + " ".join(args))
        if contains:
            self.assertIn(contains, p.stderr, " ".join(args))
        return p

    # H6 / L13 ------------------------------------------------------------------
    def test_values_that_were_accepted_or_crashed(self):
        for args in (("scan", "--max-concurrent", "0"), ("scan", "--workers", "-3"),
                     ("run", "--wave", "0", "--parallel", "0"), ("run", "--wave", "0", "--max-attempts", "0"),
                     ("run", "--wave", "0", "--timeout", "-1"), ("compact", "--compact-threshold", "5"),
                     ("query", "stats", "--budget", "-5")):
            with self.subTest(args=args):
                self.assertFails(*args)

    def test_prompts_and_run_name_the_valid_choices(self):
        self.assertFails("prompts", "--node", "nope", contains="root")
        self.assertFails("prompts", "--wave", "9", contains="Valid")
        self.assertFails("run", "--wave", "9", "--runner-cmd", "true")
        self.assertFails("run", "--wave", "0", "--runner-cmd", "")

    def test_missing_lesson_cut_is_an_error(self):
        self.assertFails("prompts", "--lessons", "5", contains="no such lesson-set cut")
        self.assertFails("run", "--wave", "0", "--lessons", "5", "--runner-cmd", "true",
                         contains="no such lesson-set cut")
        self.assertFails("holdout", "--lessons", "5", contains="no such lesson-set cut")
        self.assertFails("lessons", "show", "--version", "5", contains="no such lesson-set cut")

    def test_flags_that_do_not_apply_are_errors(self):  # E8
        self.assertFails("lessons", "cut", "--version", "2")
        self.assertFails("lessons", "show", "--reason", "x")
        self.assertFails("selftest", "--determinism", "TMP", "--min-tests", "3")
        self.assertFails("install", "--remove-harness", "--strict", "TMP")

    # H5 -----------------------------------------------------------------------
    def test_short_shas_are_accepted_everywhere(self):
        full = self.run_cdp("diff", "--old-sha", self.c1, "--new-sha", self.c2)
        short = self.run_cdp("diff", "--old-sha", self.c1[:8], "--new-sha", self.c2[:7])
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertEqual(short.stdout, full.stdout)
        self.assertEqual(self.run_cdp("query", "stats", "--as-of", self.c1[:8]).returncode, 0)
        self.assertEqual(self.run_cdp("gc", "--dry-run", "--head-sha", self.c2[:8]).returncode, 0)
        for flag in ("--pin", "--unpin"):
            p = self.run_cdp("gc", flag, self.c1[:8])
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_short_sha_rollback_to_run(self):
        p = self.run_cdp("rollback", "--to-run", self.c2[:8])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("cdp-" + self.c2[:12], p.stdout)
        self.run_cdp("rollback", "--undo")

    def test_unknown_prefix_lists_candidates(self):
        for args in (("diff", "--old-sha", "deadbe"), ("gc", "--pin", "deadbe"), ("gc", "--head-sha", "deadbe")):
            with self.subTest(args=args):
                self.assertFails(*args, contains=self.c1[:12])
        self.assertFails("query", "stats", "--as-of", "deadbe")
        self.assertFails("rollback", "--to-run", "deadbe")

    # H7 -----------------------------------------------------------------------
    def test_user_errors_have_messages_not_tracebacks(self):
        for args in (("validate", "TMP/bad.json"),
                     ("validate", "TMP/missing.json"), ("validate", "TMP"),
                     ("export", "--out", "TMP/afile"),
                     ("export", "--format", "bogus", "--out", "TMP/o"),
                     ("docs", "--out", "TMP/afile"),
                     ("diff", "TMP/nonexistent", "TMP/nonexistent2"), ("diff", "TMP"),
                     ("query", "bogus"), ("help", "nope"),
                     ("answer", "root/nope", "--subject", "s", "--kind", "naming", "--claim", "c",
                      "--anchor", "garbage"),
                     ("selftest", "--determinism", "TMP/nonexistent"), ("install", "TMP/nonexistent")):
            with self.subTest(args=args):
                self.assertFails(*args)

    def test_validate_reports_a_non_object_patch_as_a_failure(self):
        p = self.run_cdp("validate", "TMP/arr.json")
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("FAIL", p.stdout)

    # I4 -----------------------------------------------------------------------
    def test_db_with_a_wrong_path_errors_and_creates_nothing(self):
        missing = self.tmp / "nowhere" / "index.db"
        for args in (("gc", "--db", str(missing)), ("gc", "--dry-run", "--db", str(missing)),
                     ("compact", "--db", str(missing)),
                     ("export", "--db", str(missing), "--out", str(self.tmp / "exp")),
                     ("link", "scan", "--db", str(missing)), ("link", "query", "--service", "s", "--db", str(missing)),
                     ("gc", "--db", str(self.tmp))):
            with self.subTest(args=args):
                self.assertFails(*args, contains="--db")
        self.assertFalse(missing.exists())
        self.assertFalse(missing.parent.exists())
        self.assertFalse((self.tmp / "exp").exists())

    def test_db_pointing_at_the_real_store_still_works(self):
        db = self.cdp.home / "index.db"
        p = self.run_cdp("export", "--db", str(db), "--out", str(self.tmp / "exp-real"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(any((self.tmp / "exp-real").iterdir()))


class FoldOrderTest(unittest.TestCase):
    def test_failed_scope_reason_does_not_depend_on_log_order(self):
        from cdp.state import fold
        patches = [{"node": "root/a", "run_id": "cdp-r", "status": "failed", "error": err, "patch_no": n,
                    "schema_version": "1.0.0", "claims": [], "unknowns": []}
                   for n, err in ((1, "timed out"), (2, "wrote no patch"))]
        fwd = fold(patches, {"symbols": {}}, None)["unknowns"]
        rev = fold(list(reversed(patches)), {"symbols": {}}, None)["unknowns"]
        self.assertEqual(json.dumps(fwd, sort_keys=True), json.dumps(rev, sort_keys=True))


class ValidateSchemaTest(unittest.TestCase):
    def test_non_object_patches_are_reported_not_raised(self):
        from cdp.schema import Validator, schema_path, validate_patch
        from cdp.util import SKILL_ROOT
        v = Validator.load(schema_path(SKILL_ROOT))
        for bad in ([1], "x", 5, None, {"claims": 5}):
            self.assertTrue(validate_patch(bad, v), bad)


class GeneratedLabelTest(unittest.TestCase):
    """B18: only genuinely generated modules are labelled "generated at build time"."""

    def build(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = L.new_repo(Path(tmp.name), "pool")
        java = "package p;\npublic class C%d {}\n"
        repo.write("sql-pool/build.gradle", "// parent\n")
        repo.write("sql-pool/settings.gradle", "include 'api'\n")
        for i in range(60):  # nested module: its files must not be counted against the parent
            repo.write("sql-pool/api/src/main/java/p/A%d.java" % i, java % i)
        repo.write("sql-pool/api/build.gradle", "// api\n")
        repo.write("sql-pool/client/build.gradle", "// generated client\n")
        repo.write("sql-pool/client/README.md", "client\n")
        repo.commit("init")
        # untracked output a normal build leaves behind: classes and a dependency tree
        for i in range(60):
            repo.write("sql-pool/api/build/classes/p/A%d.class" % i, "x")
            repo.write("sql-pool/api/node_modules/dep/f%d.js" % i, "x")
        # a module whose Java is generated at build time: untracked sources, nothing authored
        for i in range(60):
            repo.write("sql-pool/client/build/generated/src/main/java/p/G%d.java" % i, java % i)
        return repo

    def test_only_the_generated_module_is_flagged(self):
        from cdp.inventory import build_inventory
        repo = self.build()
        mods = {m["name"]: m for m in build_inventory(repo.path)["modules"]}
        self.assertFalse(mods["sql-pool"]["generated_suspect"], mods["sql-pool"])
        self.assertFalse(mods["sql-pool/api"]["generated_suspect"], mods["sql-pool/api"])
        self.assertTrue(mods["sql-pool/client"]["generated_suspect"], mods["sql-pool/client"])
        self.assertEqual(mods["sql-pool"]["on_disk"], 2)  # its own files, not its children's


if __name__ == "__main__":
    unittest.main()
