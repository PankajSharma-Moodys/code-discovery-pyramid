"""`cdp install` ships the cdp-diagrams mod (RESEARCH_DIAGRAM_MOD_V2.md item f): the runtime files
only, replaced whole on re-install, skipped by `--no-diagrams` and on `--self`, untouched by
`--remove-harness` (which, like for the skill, removes wiring and leaves copied files)."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)
from cdp import install_extras
from cdp.cli import main


def _files(root: Path) -> set:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


class DiagramModInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.target = self.root / "target"
        self.target.mkdir()
        self.mod = self.target / ".claude" / "cdp-diagrams"

    def install(self, *argv: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["install", str(self.target), *argv]), 0)
        return out.getvalue()

    def fake_source(self) -> Path:
        """A mod tree carrying every development-only path the copy must leave out."""
        src = self.root / "src" / "cdp-diagrams"
        for rel in (".claude-plugin/plugin.json", ".claude-plugin/types/claude.d.ts", "hooks/hooks.json",
                    "hooks/register.tsx", "hooks/lib/types/keep.ts", "tests/parse.test.ts", "dev/probe.sh",
                    "tsconfig.json", ".gitignore", "node_modules/x/index.js", "hooks/node_modules/y.js"):
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_text("{}\n", encoding="utf-8")
        return src

    def test_real_mod_is_copied_with_runtime_files_only(self) -> None:
        out = self.install()
        files = _files(self.mod)
        self.assertIn(".claude-plugin/plugin.json", files)
        self.assertIn("hooks/hooks.json", files)
        self.assertTrue(any(f.startswith("hooks/") and f.endswith((".ts", ".tsx")) for f in files))
        self.assertEqual([f for f in files if not f.startswith(("hooks/", ".claude-plugin/plugin.json"))], [])
        self.assertIn("next      start Claude with: claude --plugin-dir %s" % self.mod.resolve(), out)

    def test_development_paths_are_excluded(self) -> None:
        with mock.patch.object(install_extras, "DIAGRAMS_SOURCE", self.fake_source()):
            self.install()
        self.assertEqual(_files(self.mod), {".claude-plugin/plugin.json", "hooks/hooks.json",
                                            "hooks/register.tsx", "hooks/lib/types/keep.ts"})

    def test_reinstall_replaces_the_copy_whole(self) -> None:
        self.install()
        before = _files(self.mod)
        (self.mod / "hooks" / "stale.ts").write_text("old\n", encoding="utf-8")
        (self.mod / "hooks" / "hooks.json").write_text("edited\n", encoding="utf-8")
        self.install()
        self.assertEqual(_files(self.mod), before)
        self.assertEqual((self.mod / "hooks" / "hooks.json").read_bytes(),
                         (install_extras.DIAGRAMS_SOURCE / "hooks" / "hooks.json").read_bytes())

    def test_no_diagrams_skips_it(self) -> None:
        out = self.install("--no-diagrams")
        self.assertFalse(self.mod.exists())
        self.assertNotIn("--plugin-dir", out)
        self.assertTrue((self.target / ".claude" / "skills" / "cdp" / "run.py").is_file())

    def test_a_copy_without_the_mod_says_it_skipped(self) -> None:
        with mock.patch.object(install_extras, "DIAGRAMS_SOURCE", self.root / "absent"):
            out = self.install()
        self.assertFalse(self.mod.exists())
        self.assertIn("skipped   diagram mod", out)

    def test_remove_harness_leaves_the_mod_like_the_skill(self) -> None:
        self.install("--harness")
        files = _files(self.mod)
        self.install("--remove-harness")
        self.assertEqual(_files(self.mod), files)
        self.assertTrue((self.target / ".claude" / "skills" / "cdp").is_dir())

    def test_self_install_does_not_copy_the_mod(self) -> None:
        from cdp import install as install_mod

        with mock.patch.object(install_mod, "copy_distribution"), \
                mock.patch.object(install_mod, "register_leaf_agent"), \
                mock.patch.object(install_mod, "install_diagrams") as diagrams:  # writes nothing here
            install_mod.install(SKILL_ROOT)
        diagrams.assert_not_called()


if __name__ == "__main__":
    unittest.main()
