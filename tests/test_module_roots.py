"""Module detection at the scan root — `PHASE/phase_1_plan.md` M1.1.

Three layouts, and the whole fix is the distinction between the first two:

    solorepo   one manifest at the scan root, none beneath it
    anonrepo   the same, but the manifest states no name
    minirepo   a root manifest *and* sub-manifests -- an aggregator

The third is the regression that matters. M1.1 touches the shared path, and the
failure mode it could introduce is collapsing a monorepo into one module named
after its root `settings.gradle`.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, have_git, make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import _structural_unknowns
from cdp.inventory import ROOT_MODULE


class SingleModuleRepoTest(unittest.TestCase):
    """`--repo` pointed at one service: the case hit in the field."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name), "solorepo")
        cls.pipeline = Pipeline(cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_exactly_one_module(self) -> None:
        modules = self.pipeline.inventory["modules"]
        self.assertEqual([m["name"] for m in modules], ["solo-service"])

    def test_named_from_the_manifest_not_the_directory(self) -> None:
        root = self.pipeline.inventory["root_module"]
        self.assertTrue(root["is_module"])
        self.assertTrue(root["named"])
        self.assertEqual(root["name"], "solo-service")
        self.assertEqual(root["manifest"], "pom.xml")

    def test_no_bogus_directory_module(self) -> None:
        """The old fallback invented one module per top-level directory, so a
        Maven project became a module called `src` — a name that appears in no
        manifest and can never be the target of a declared edge."""
        names = {m["name"] for m in self.pipeline.inventory["modules"]}
        self.assertNotIn("src", names)
        self.assertNotIn(ROOT_MODULE, names)

    def test_the_module_owns_every_file(self) -> None:
        files = self.pipeline.inventory["files"]
        self.assertTrue(files)
        self.assertEqual({f["module"] for f in files}, {"solo-service"})

    def test_the_module_carries_its_manifest(self) -> None:
        module = self.pipeline.inventory["modules"][0]
        self.assertEqual(module["manifests"], ["pom.xml"])
        self.assertEqual(module["path"], "")
        # A named root module is a module, so it gets a census of its own.
        self.assertIn("on_disk", module)

    def test_scopes_split_on_the_real_path_prefix(self) -> None:
        """The module's name (`solo-service`) is not its path prefix (``).
        Deriving the prefix from the name would look for `solo-service/...`,
        match nothing, and defeat every split below the module."""
        scopes = self.pipeline.partition["scopes"]
        self.assertTrue(scopes)
        for scope in scopes:
            self.assertEqual(scope["module"], "solo-service")
            for path in scope["files"]:
                self.assertFalse(path.startswith("solo-service/"), path)

    def test_declared_dependencies_are_still_read(self) -> None:
        """The third-party dependency is a declared fact even though it is not
        an inter-module edge; a single-module repository has none of those."""
        declared = self.pipeline.extraction["declared_deps"]
        self.assertIn("jackson-databind", declared.get("solo-service", []))
        self.assertEqual(self.pipeline.graph["declared"], [])

    def test_no_identity_unknown_is_raised(self) -> None:
        unknowns = _structural_unknowns(
            self.pipeline.inventory, self.pipeline.xref, self.pipeline.graph
        )
        self.assertNotIn(
            "What is this module called?", [u["question"] for u in unknowns]
        )


class UnnameableRootTest(unittest.TestCase):
    """A root manifest that states no name degrades to an unknown, not a guess."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name), "anonrepo")
        cls.pipeline = Pipeline(cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_root_is_one_module_but_anonymous(self) -> None:
        root = self.pipeline.inventory["root_module"]
        self.assertTrue(root["is_module"])
        self.assertFalse(root["named"])
        self.assertIsNone(root["name"])
        self.assertEqual([m["name"] for m in self.pipeline.inventory["modules"]],
                         [ROOT_MODULE])

    def test_the_directory_name_is_never_borrowed(self) -> None:
        names = {m["name"] for m in self.pipeline.inventory["modules"]}
        self.assertNotIn("anonrepo", names)
        self.assertNotIn("src", names)

    def test_a_structural_unknown_states_the_gap(self) -> None:
        unknowns = _structural_unknowns(
            self.pipeline.inventory, self.pipeline.xref, self.pipeline.graph
        )
        matching = [u for u in unknowns if u["question"] == "What is this module called?"]
        self.assertEqual(len(matching), 1, unknowns)
        self.assertIn("build.gradle", matching[0]["why_unresolved"])


class AggregatorRootTest(unittest.TestCase):
    """The regression M1.1 is most likely to cause.

    `minirepo` has `build.gradle` + `settings.gradle` at its root *and*
    `core/build.gradle` and `web/build.gradle` beneath. The root must stay the
    root scope: a rule that fired on any root manifest would collapse it into
    one module called `mini`.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name))
        cls.pipeline = Pipeline(cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_root_is_not_a_module(self) -> None:
        root = self.pipeline.inventory["root_module"]
        self.assertFalse(root["is_module"])
        self.assertIn("sub-manifests", root["reason"])

    def test_sub_manifests_still_define_the_modules(self) -> None:
        names = {m["name"] for m in self.pipeline.inventory["modules"]}
        self.assertEqual(names, {ROOT_MODULE, "core", "web"})

    def test_root_scope_still_owns_the_unclaimed_files(self) -> None:
        by_module = {f["path"]: f["module"] for f in self.pipeline.inventory["files"]}
        self.assertEqual(by_module["settings.gradle"], ROOT_MODULE)
        self.assertEqual(by_module["core/build.gradle"], "core")

    def test_the_root_scope_gets_no_census_of_its_own(self) -> None:
        root = [m for m in self.pipeline.inventory["modules"] if m["name"] == ROOT_MODULE][0]
        self.assertNotIn("on_disk", root)


if __name__ == "__main__":
    unittest.main()
