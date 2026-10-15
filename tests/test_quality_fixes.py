"""Quality fixes from the 2026-10-15 review (REVIEW_FINDINGS.md, Quality #1, #2a, #3-#11).

Each class reproduces one finding on a small repository and asserts the corrected answer.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline

from cdp.query import _dispatch, dispatch
from cdp.query.budget import Budget
from cdp.query.lookup import q_table
from cdp.query.views import _text
from cdp.query.lookup import q_symbol
from cdp.query.render import render


class _Store:
    """Enough of a query Store for `symbol` and `trace`."""

    def __init__(self, p: Pipeline) -> None:
        self.extraction, self.xref = p.extraction, p.xref
        self.inventory, self.graph, self.dataflow = p.inventory, p.graph, p.dataflow
        self.state = {"claims": [], "unknowns": [], "provenance": {}}
        self._cache: dict = {}


def _repo(tmp: Path, files: dict) -> Path:
    for rel, text in files.items():
        f = tmp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp)}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(tmp)] + args, check=True, capture_output=True, env=env)
    return tmp


class _RepoCase(unittest.TestCase):
    FILES: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), cls.FILES))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class StaticImportConstantsInRoutes(_RepoCase):
    """#1: `@Path(EXPOSURE_PATH)` with `import static ...ApiConstants.EXPOSURE_PATH` was read as
    `${BundlesResource.EXPOSURE_PATH}` and reported as a constant "not defined anywhere"."""

    FILES = {
        "src/main/java/a/ApiConstants.java": (
            "package a;\n"
            "public final class ApiConstants {\n"
            "  public static final String ROOT = \"/v1\";\n"
            "  public static final String EXPOSURE_PATH = ROOT + \"/bundles\";\n"
            "}\n"),
        "src/main/java/b/Paths.java": (
            "package b;\n"
            "import static a.ApiConstants.ROOT;\n"
            "public final class Paths {\n"
            "  public static final String JOBS = ROOT + \"/jobs\";\n"
            "}\n"),
        "src/main/java/b/BundlesResource.java": (
            "package b;\n"
            "import static a.ApiConstants.EXPOSURE_PATH;\n"
            "import javax.ws.rs.GET;\n"
            "import javax.ws.rs.Path;\n"
            "@Path(EXPOSURE_PATH)\n"
            "public class BundlesResource {\n"
            "  static final String LOCAL = \"/own\";\n"
            "  @GET @Path(\"/{id}\") public String get() { return \"\"; }\n"
            "  @GET @Path(LOCAL) public String own() { return \"\"; }\n"
            "  @GET @Path(Paths.JOBS) public String jobs() { return \"\"; }\n"
            "}\n"),
        "src/main/java/b/WildResource.java": (
            "package b;\n"
            "import static a.ApiConstants.*;\n"
            "import javax.ws.rs.GET;\n"
            "import javax.ws.rs.Path;\n"
            "@Path(ROOT)\n"
            "public class WildResource {\n"
            "  @GET @Path(\"/w\") public String get() { return \"\"; }\n"
            "}\n"),
    }

    def test_routes_resolve_through_static_import(self):
        routes = {r["route"].replace("//", "/") for r in self.p.xref["routes"]}
        self.assertIn("/v1/bundles/{id}", routes)
        self.assertIn("/v1/bundles/own", routes)      # the class's own constant still wins
        self.assertIn("/v1/bundles/v1/jobs", routes)  # a constant built from a static import
        self.assertIn("/v1/w", routes)                 # the file's only `import static a.ApiConstants.*`
        self.assertEqual(self.p.xref["unresolved_routes"], [])


class InheritedLoggerCall(_RepoCase):
    """#3: `logger.info` where `logger` comes from a `StrictLogging` mixin was listed in `symbol`
    as `Svc#info`: the chain's base type, credited with a method it does not declare."""

    FILES = {
        "src/main/scala/a/Svc.scala": (
            "package a\n"
            "import com.typesafe.scalalogging.StrictLogging\n"
            "class Repo { def find(x: String): Repo = this; def name: String = \"\" }\n"
            "class Svc(repo: Repo) extends StrictLogging {\n"
            "  val other: Repo = new Repo\n"
            "  def run(x: String): String = {\n"
            "    logger.info(s\"x $x\")\n"
            "    repo.find(x).find(x)\n"
            "    \"\"\n"
            "  }\n"
            "}\n"),
        "src/main/java/b/Job.java": (
            "package b;\n"
            "import static org.mockito.Mockito.when;\n"
            "public class Job extends org.quartz.Base {\n"
            "  void own() {}\n"
            "  void run() { when(null); helper(); own(); }\n"
            "}\n"),
    }

    def test_bare_call_not_credited_to_class(self):
        found = q_symbol(_Store(self.p), "b.Job#run", exact=True)["found"]
        self.assertEqual(found[0]["body"][0].get("calls"), ["Job#own"])

    def test_inherited_member_call_not_credited_to_class(self):
        found = q_symbol(_Store(self.p), "a.Svc#run", exact=True)["found"]
        calls = [c for row in found[0]["body"] for c in row.get("calls", [])]
        self.assertNotIn("Svc#info", calls)
        self.assertIn("Repo#find", calls)


class SymbolClaimFilters(_RepoCase):
    """#4: `symbol` embedded test-only and `library:` claims that `query claims` drops by default."""

    FILES = {"src/main/java/a/Mapper.java": "package a;\npublic class Mapper {}\n",
             "src/test/java/a/MapperTest.java": "package a;\npublic class MapperTest {}\n"}

    def store(self):
        st = _Store(self.p)
        ev = lambda f: [{"file": f, "line": 2}]
        st.state["claims"] = [
            {"kind": "data_model", "subject": "a.Mapper", "statement": "Mapper is a model", "evidence": ev(
                "src/main/java/a/Mapper.java")},
            {"kind": "data_model", "subject": "a.Mapper -> library:org.mapstruct.Mapper",
             "statement": "Mapper is converted to Mapper", "evidence": ev("src/main/java/a/Mapper.java")},
            {"kind": "data_model", "subject": "a.MapperTest", "statement": "MapperTest checks Mapper",
             "evidence": ev("src/test/java/a/MapperTest.java")},
        ]
        return st

    def test_same_defaults_as_claims(self):
        out = _dispatch(self.store(), "symbol", "a.Mapper", exact=True)
        self.assertEqual([c["subject"] for c in out["found"][0]["claims"]], ["a.Mapper"])
        out = _dispatch(self.store(), "symbol", "a.Mapper", exact=True, include_tests=True, include_library=True)
        self.assertEqual(out["found"][0]["claims_count"], 3)

    def test_default_filters_note_names_library(self):
        out = dispatch(self.store(), "symbol", "a.Mapper", exact=True, format="json")
        self.assertIn("library", out.get("default_filters", ""))


class OverloadsAreNotCollisions(_RepoCase):
    """#2a: an overloaded method was shown as `collision: true` ("no winner is picked")."""

    FILES = {
        "src/main/java/a/Svc.java": (
            "package a;\n"
            "public class Svc {\n"
            "  public void put(String s) {}\n"
            "  public void put(String s, int n) {}\n"
            "}\n"),
        "src/main/java/a/Twice.java": "package a;\npublic class Twice {}\n",
        "src/test/java/a/Twice.java": "package a;\npublic class Twice {}\n",
    }

    def test_overloads_counted_not_collided(self):
        found = q_symbol(_Store(self.p), "a.Svc#put", exact=True)["found"][0]
        self.assertEqual((found["collision"], found.get("overloads")), (False, 2))
        text = render({"query": "symbol", "name": "a.Svc#put", "match": "exact", "found": [found]})
        self.assertIn("overloads: 2", text)
        self.assertNotIn("no winner", text)

    def test_real_duplicate_still_a_collision(self):
        found = q_symbol(_Store(self.p), "a.Twice", exact=True)["found"][0]
        self.assertTrue(found["collision"])
        self.assertIsNone(found.get("overloads"))


class MapperClaimsNeedTheMarker(_RepoCase):
    """#5: importing `org.mapstruct.factory.Mappers` (a test getting a mapper) produced "converted to
    factory by a mapper": a representation claim from the import alone."""

    FILES = {
        "src/main/java/a/RowMapper.java": (
            "package a;\n"
            "import org.mapstruct.Mapper;\n"
            "@Mapper\n"
            "public interface RowMapper {\n"
            "  Dto toDto(Row r);\n"
            "}\n"),
        "src/main/java/a/Row.java": "package a;\npublic class Row {}\n",
        "src/main/java/a/Dto.java": "package a;\npublic class Dto {}\n",
        "src/main/java/a/Use.java": (
            "package a;\n"
            "import org.mapstruct.factory.Mappers;\n"
            "public class Use { RowMapper m = Mappers.getMapper(RowMapper.class); }\n"),
    }

    def test_only_marked_files_claim_a_conversion(self):
        subjects = [c["subject"] for c in self.p.claims_of("data_model") if "converted to" in c["statement"]]
        self.assertIn("a.Row -> a.Dto", subjects)
        self.assertFalse([s for s in subjects if s.startswith("a.Use")], subjects)


class NestedGradleBuilds(_RepoCase):
    """#6: in a repository of several Gradle builds, `project(':api:common')` was looked up from the
    repository root, not from `svc/settings.gradle`, so every such dependency was missed and the
    imports it explains were reported as "imported but not declared" (also `api(project(..))`).
    #7: `platform(project(':svc-bom'))` was reported as "declared but never imported"."""

    FILES = {
        "svc/settings.gradle": "include ':svc-bom'\ninclude ':api:common'\ninclude ':core:engine'\n",
        "svc/svc-bom/build.gradle": "plugins { id 'java-platform' }\n",
        "svc/api/common/build.gradle": "dependencies {\n  implementation platform(project(':svc-bom'))\n}\n",
        "svc/api/common/src/main/java/a/common/Util.java": "package a.common;\npublic class Util {}\n",
        "svc/core/engine/build.gradle": (
            "dependencies {\n"
            "  implementation platform(project(':svc-bom'))\n"
            "  api(project(':api:common'))\n"
            "}\n"),
        "svc/core/engine/src/main/java/a/engine/Run.java": (
            "package a.engine;\nimport a.common.Util;\npublic class Run { Util u; }\n"),
    }

    def test_paths_resolve_against_nearest_settings(self):
        div = self.p.graph["divergence"]
        self.assertEqual(div["observed_not_declared"], [])
        self.assertIn({"from": "svc/core/engine", "to": "svc/api/common"}, self.p.graph["declared"])

    def test_platform_edge_kept_and_labelled_not_an_anomaly(self):
        self.assertIn({"from": "svc/api/common", "to": "svc/svc-bom", "uses": "version platform"},
                      self.p.graph["declared"])
        self.assertEqual(self.p.graph["divergence"]["declared_not_observed"], [])


class BudgetedTables(_RepoCase):
    """#10: `--budget 5` said "56 rows ... left out 69 ... budget=74 returns every row": dropped tables
    counted one row each while their own sites went uncounted, so 74 did not return every row.
    #11: a table row whose citation lists the budget had emptied was listed with no file:line."""

    FILES = {
        "src/main/java/a/Alpha.java": ("package a;\nimport javax.persistence.*;\n"
                                     "@Entity @Table(name = \"alpha\")\npublic class Alpha { @Id Long id; }\n"),
        "src/main/java/a/Beta.java": ("package a;\nimport javax.persistence.*;\n"
                                     "@Entity @Table(name = \"beta\")\npublic class Beta { @Id Long id; }\n"),
        "src/main/java/a/Gamma.java": ("package a;\nimport javax.persistence.*;\n"
                                     "@Entity @Table(name = \"gamma\")\npublic class Gamma { @Id Long id; }\n"),
    }

    def test_note_agrees_with_counts(self):
        b = Budget(2)
        out = q_table(_Store(self.p), budget=b)
        self.assertEqual((out["count"], len(out["tables"])), (3, 2))
        note = out["budget_note"]
        self.assertIn("1 of 3 table(s)", note)
        self.assertNotIn("returns every row.", note)
        self.assertIn("left out %d row(s)" % out["elided"], note)

    def test_budgeted_row_keeps_its_citation(self):
        out = q_table(_Store(self.p), budget=Budget(1))
        self.assertEqual(out["tables"][0]["evidence"], [])          # the budget emptied the list ...
        self.assertTrue(out["tables"][0]["at"].startswith("src/main/java/a/"))   # ... not the row's cite
        text = dispatch(_Store(self.p), "table", budget=1, format="text")
        text = text if isinstance(text, str) else text.get("text", "")
        self.assertIn(".java:", text)


class PagedAnswerIsNotComplete(unittest.TestCase):
    """#8: a paged answer (`shown 1-57` of 91) printed a bare `elided: 0`, which help said means
    "the list is complete"."""

    def test_paged_elided_line_says_so(self):
        text = _text("routes", {"query": "routes", "count": 91, "shown": "1-57", "elided": 0, "next": "x"}, "list")
        self.assertIn("elided: 0 (this page is rows 1-57 of 91", text)
        whole = _text("routes", {"query": "routes", "count": 3, "elided": 0}, "list")
        self.assertIn("elided: 0", whole)
        self.assertNotIn("this page", whole)

    def test_help_no_longer_promises_completeness_alone(self):
        from cdp.helpdoc import GUIDANCE
        text = "\n".join(GUIDANCE["reading an answer honestly"])
        self.assertNotIn("elided: 0    the list is complete.", text)
        self.assertIn("next", text)


class StatsListsLanguages(_RepoCase):
    """#9: text `stats` left out the languages its help promises."""

    FILES = {"a.py": "x = 1\n", "src/main/java/a/A.java": "package a;\npublic class A {}\n"}

    def test_languages_line(self):
        from cdp.query.render import render
        from cdp.query.stats import q_stats
        st = _Store(self.p)
        st.manifest, st.partition = {}, self.p.partition
        line = [l for l in render(q_stats(st)).splitlines() if l.startswith("languages")]
        self.assertEqual(len(line), 1)
        self.assertIn("java 1", line[0])
        self.assertIn("python 1", line[0])


if __name__ == "__main__":
    unittest.main()
