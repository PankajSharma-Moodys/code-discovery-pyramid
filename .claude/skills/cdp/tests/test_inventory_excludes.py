"""AI-tool/editor scaffolding exclusion -- found live: dispatching a leaf
agent against a real target's `.cursor/` scope burned two real model calls
and failed both times on schema violations, because there was nothing
architectural in Cursor rule files for a leaf to honestly extract. A
denylist, made configurable per the user's request: built-in defaults,
extendable via `.cdp.toml`'s `exclude` list or `cdp scan --exclude`, never
replacing the defaults.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp.inventory import DEFAULT_EXCLUDES, build_inventory
from cdp.store.registry import team_excludes


def _add_file(repo: Path, rel: str, content: str = "x\n") -> None:
    """`build_inventory` reads `git ls-files` -- a file only on disk, never
    committed, is invisible to it and to the exclusion logic alike."""
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "cdp@example.invalid",
           "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "cdp@example.invalid",
           "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(repo)}
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", "commit",
                    "-q", "-m", "add " + rel], check=True, capture_output=True, env=env)


class DefaultExcludesTest(unittest.TestCase):
    def test_dot_claude_and_dot_cursor_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            _add_file(repo, ".claude/rules/security.md")
            _add_file(repo, ".cursor/rules/security.mdc")
            inventory = build_inventory(repo)
        paths = [f["path"] for f in inventory["files"]]
        self.assertNotIn(".claude/rules/security.md", paths)
        self.assertNotIn(".cursor/rules/security.mdc", paths)
        self.assertEqual(inventory["excluded"]["count"], 2)
        self.assertIn(".claude/rules/security.md", inventory["excluded"]["paths"])
        self.assertIn(".cursor/rules/security.mdc", inventory["excluded"]["paths"])

    def test_segment_exact_match_not_substring(self) -> None:
        """`.cursorstuff/` must survive a `.cursor` entry -- a substring match
        would silently drop unrelated directories that merely start with the
        same characters."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            _add_file(repo, ".cursorstuff/real_source.py")
            inventory = build_inventory(repo)
        paths = [f["path"] for f in inventory["files"]]
        self.assertIn(".cursorstuff/real_source.py", paths)
        self.assertEqual(inventory["excluded"]["count"], 0)

    def test_nested_occurrence_is_also_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            _add_file(repo, "core/.vscode/settings.json")
            inventory = build_inventory(repo)
        paths = [f["path"] for f in inventory["files"]]
        self.assertNotIn("core/.vscode/settings.json", paths)


class ExtraExcludesTest(unittest.TestCase):
    def test_extra_excludes_add_without_removing_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            _add_file(repo, ".claude/rules/security.md")
            _add_file(repo, ".my-team-tool/notes.md")
            inventory = build_inventory(repo, extra_excludes=(".my-team-tool",))
        paths = [f["path"] for f in inventory["files"]]
        self.assertNotIn(".claude/rules/security.md", paths)  # default still applies
        self.assertNotIn(".my-team-tool/notes.md", paths)      # extra applies too
        self.assertEqual(inventory["excluded"]["count"], 2)


class TeamConfigExcludeTest(unittest.TestCase):
    def test_cdp_toml_exclude_list_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / ".cdp.toml").write_text(
                'exclude = [".my-team-tool"]\n', encoding="utf-8"
            )
            self.assertEqual(team_excludes(repo), [".my-team-tool"])

    def test_no_cdp_toml_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            self.assertEqual(team_excludes(repo), [])


if __name__ == "__main__":
    unittest.main()
