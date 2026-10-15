"""B13-B15: `link` usage error and self-link labelling, githook --state-dir, install/remove edges."""

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from cdp import githooks, install as install_mod
from cdp.cli import main
from cdp.link import scan_links, summarise
from cdp.util import SKILL_ROOT


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class LinkTest(unittest.TestCase):
    def test_bare_link_is_a_one_line_usage_error(self):
        code, out, err = _run("link")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1)
        for sub in ("scan", "query", "refresh", "prompts", "collect", "run"):
            self.assertIn(sub, err)

    def test_self_links_are_counted_apart_from_cross_module(self):
        def edge(src, tgt, ch, file, line):
            return {"source": src, "target": tgt, "channel": ch, "module": "m", "confidence": "high",
                    "anchor": {"file": file, "line": line}}
        snap = {"repo": "r", "head": "h", "dataflow": {"edges": [
            edge("OrderRepo#save", "table:orders", "persist", "OrderRepo.java", 9),
            edge("mig", "table:orders", "schema_own", "db/schema.sql", 1)]}}
        text = "\n".join(summarise(scan_links([snap])))
        self.assertIn("1 of those are `self` links", text)
        self.assertIn("0 cross-module", text)


class GithookStateDirTest(unittest.TestCase):
    def _script(self, state_dir):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "r"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            githooks.install(repo, state_dir)
            return (repo / ".git" / "hooks" / "post-commit").read_text()

    def test_state_dir_is_baked_in_and_quoted(self):
        text = self._script(Path("/tmp/my state's dir"))
        self.assertIn("--state-dir '/tmp/my state'\"'\"'s dir'", text)

    def test_without_state_dir_the_hook_is_unchanged(self):
        self.assertNotIn("--state-dir", self._script(None))


class InstallTest(unittest.TestCase):
    def test_remove_harness_removes_the_agents_md_it_wrote_only(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d)
            (t / "AGENTS.md").write_text("mine\n")
            install_mod.remove_harness(t)
            self.assertEqual((t / "AGENTS.md").read_text(), "mine\n")
            (t / "AGENTS.md").write_bytes((SKILL_ROOT / "AGENTS.md").read_bytes())
            self.assertTrue(any("AGENTS.md" in n for n in install_mod.remove_harness(t)))
            self.assertFalse((t / "AGENTS.md").exists())

    def test_remove_harness_on_the_skill_root_keeps_its_agents_md(self):
        self.assertEqual(install_mod.remove_agents_md(SKILL_ROOT), [])
        self.assertTrue((SKILL_ROOT / "AGENTS.md").is_file())

    def test_install_refuses_a_state_dir_target(self):
        for markers in (("index.db.migrate",), ("index.db", "work/")):
            with tempfile.TemporaryDirectory() as d:
                for m in markers:
                    (Path(d) / m).mkdir() if m.endswith("/") else (Path(d) / m).write_text("")
                code, _, err = _run("install", d, "--framework", "none")
                self.assertEqual(code, 2)
                self.assertIn("state directory", err)
                self.assertFalse((Path(d) / ".claude").exists())

    def test_install_accepts_a_repo_with_its_own_index_db(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.db").write_text("")  # the app's own SQLite file
            code, _, err = _run("install", d, "--framework", "none")
            self.assertEqual(code, 0, err)
        with tempfile.TemporaryDirectory() as d:  # ... even beside a work/ folder, in a git checkout
            for name in (".git", "work"):
                (Path(d) / name).mkdir()
            (Path(d) / "index.db").write_text("")
            code, _, err = _run("install", d, "--framework", "none")
            self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
