"""P4: no crashes, safe by default (L11, J6, J3, J7, B14, I3, I6, J5).

Each test drives the real CLI (or server) on a temp git repo and checks what ends up on disk."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git, make_repo

import repo_layouts as L
from repo_layouts import Cdp

RUN_PY = SKILL_ROOT / "run.py"


def tree(root: Path) -> set:
    return {str(p.relative_to(root)) for p in Path(root).rglob("*")}


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()

    def cli(self, *args, env=None, cwd=None, check=False):
        proc = subprocess.run([sys.executable, str(RUN_PY), *args], capture_output=True, text=True,
                              env=dict(os.environ, **(env or {})), cwd=cwd)
        if check:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc


@unittest.skipUnless(have_git(), "needs git")
class DoctorModelNameTest(TmpCase):
    """L11: `doctor --model` became a file name unsanitised."""

    def test_traversal_model_is_rejected_and_nothing_escapes(self):
        repo = make_repo(self.tmp)
        home = self.tmp / "home"
        self.cli("scan", "--repo", str(repo), "--state-dir", str(home), "--quiet", check=True)
        runner = self.tmp / "noop.py"
        runner.write_text("import sys\n")
        outside = self.tmp / "escaped.json"
        for label in ("../../../../../escaped", str(outside.with_suffix("")), "a/b", ".."):
            before = tree(self.tmp)
            proc = self.cli("doctor", "--repo", str(repo), "--state-dir", str(home), "--model", label,
                            "--runner-cmd", "%s %s" % (sys.executable, runner))
            self.assertNotEqual(proc.returncode, 0, label)
            self.assertIn("not a valid name", proc.stdout + proc.stderr)
            self.assertEqual(tree(self.tmp), before, label)
        self.assertFalse(outside.exists())

    def test_plain_model_name_still_works(self):
        repo = make_repo(self.tmp)
        home = self.tmp / "home"
        self.cli("scan", "--repo", str(repo), "--state-dir", str(home), "--quiet", check=True)
        runner = self.tmp / "noop.py"
        runner.write_text("import sys\n")
        proc = self.cli("doctor", "--repo", str(repo), "--state-dir", str(home), "--model", "gpt-4.1_mini",
                        "--runner-cmd", "%s %s" % (sys.executable, runner))
        # The no-op runner yields no patch for any scope, so L9 makes this exit 1
        # ("all failed"); the point here is only that the name is accepted.
        self.assertNotIn("not a valid name", proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue(list(home.rglob("gpt-4.1_mini.json")))


@unittest.skipUnless(have_git(), "needs git")
class GoldenNameTest(TmpCase):
    """J6: `selftest --bless --golden-name` could rmtree any directory."""

    def test_traversal_name_is_rejected_and_victim_survives(self):
        repo = make_repo(self.tmp)
        victim = self.tmp / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("precious")
        for name in ("../../../../../../%s" % str(victim).lstrip("/"), str(victim), "..", "a/b"):
            proc = self.cli("selftest", "--golden", str(repo), "--bless", "--golden-name", name)
            self.assertNotEqual(proc.returncode, 0, name)
            self.assertIn("not a valid name", proc.stdout + proc.stderr)
            self.assertEqual((victim / "keep.txt").read_text(), "precious")

    def test_golden_name_without_golden_is_an_error(self):
        proc = self.cli("selftest", "--golden-name", "x", "--min-tests", "1000000")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--golden-name is only meaningful with --golden", proc.stdout + proc.stderr)

    def test_symlinked_name_inside_the_golden_dir_is_rejected(self):
        from cdp import selftest
        repo = make_repo(self.tmp)
        victim = self.tmp / "victim"
        victim.mkdir()
        link = selftest.GOLDEN_ROOT / "zz-test-link"
        link.symlink_to(victim)
        self.addCleanup(lambda: link.unlink())
        with self.assertRaises(Exception) as ctx:
            selftest.run_golden(repo, bless=True, name="zz-test-link")
        self.assertIn("outside", str(ctx.exception))
        self.assertTrue(victim.exists())


@unittest.skipUnless(have_git(), "needs git")
class RemoveHarnessTest(TmpCase):
    """J3: `install --remove-harness` removed any hook whose command contained `cdp/hook.py`."""

    USER_HOOKS = {
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "python3 /opt/audit/cdp/hook.py --audit"},
            {"type": "command", "command": "echo ok  # wraps cdp/hook.py"}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": "bash ~/mine/cdp/hook.py"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "notify-send done"}]}],
    }

    def test_user_hooks_mentioning_cdp_hook_survive_removal(self):
        repo = make_repo(self.tmp)
        settings = repo / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"hooks": self.USER_HOOKS, "permissions": {"allow": ["Bash(ls)"]}}))
        home = {"CDP_HOME": str(self.tmp / "home")}
        self.cli("install", str(repo), "--harness", env=home, check=True)
        installed = json.loads(settings.read_text())["hooks"]
        ours = [h["command"] for groups in installed.values() for g in groups for h in g["hooks"]
                if h["command"].startswith('python3 "$CLAUDE_PROJECT_DIR/.claude/skills/cdp/cdp/hook.py"')]
        self.assertGreaterEqual(len(ours), 4, installed)  # nudge, SessionStart, UserPromptSubmit, PostToolUse
        self.cli("install", str(repo), "--remove-harness", env=home, check=True)
        after = json.loads(settings.read_text())
        self.assertEqual(after["hooks"], self.USER_HOOKS)
        self.assertEqual(after["permissions"], {"allow": ["Bash(ls)"]})

    def test_reinstall_keeps_user_hooks_too(self):
        repo = make_repo(self.tmp)
        settings = repo / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"hooks": self.USER_HOOKS}))
        home = {"CDP_HOME": str(self.tmp / "home")}
        for _ in range(2):
            self.cli("install", str(repo), "--harness", env=home, check=True)
        self.cli("install", str(repo), "--remove-harness", env=home, check=True)
        self.assertEqual(json.loads(settings.read_text())["hooks"], self.USER_HOOKS)


@unittest.skipUnless(have_git(), "needs git")
class McpInputValidationTest(TmpCase):
    """J7: the MCP server accepted any input, dropped malformed JSON silently, and let
    `cdp_scan state_dir` create stores anywhere."""

    def talk(self, *lines):
        proc = subprocess.run([sys.executable, "-m", "mcp_server.server"], input="\n".join(lines) + "\n",
                              capture_output=True, text=True, cwd=str(SKILL_ROOT),
                              env=dict(os.environ, CDP_HOME=str(self.tmp / "home"), PYTHONPATH=str(SKILL_ROOT)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [json.loads(l) for l in proc.stdout.splitlines()]

    @staticmethod
    def call(i, name, args):
        return json.dumps({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                           "params": {"name": name, "arguments": args}})

    def test_bad_input_gets_json_rpc_errors(self):
        repo = make_repo(self.tmp)
        elsewhere = self.tmp / "elsewhere"
        replies = self.talk(
            "{not json", "[1, 2]",
            self.call(1, "cdp_scan", {"repo": str(repo), "state_dir": str(elsewhere)}),
            self.call(2, "cdp_query", {"repo": str(repo), "kind": "nope"}),
            self.call(3, "cdp_query", {"repo": str(repo), "kind": "trace", "max_hops": "2"}),
            self.call(4, "cdp_query", {"kind": "stats"}),
            self.call(5, "no_such_tool", {}),
            json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": [1]}),
            self.call(7, "cdp_status", {"repo": str(repo)}),
        )
        codes = [r.get("error", {}).get("code") for r in replies]
        self.assertEqual(codes[:2], [-32700, -32600])
        self.assertEqual(codes[2:8], [-32602] * 6, replies)
        self.assertIn("state_dir", replies[2]["error"]["message"])
        self.assertFalse(elsewhere.exists())
        self.assertNotIn("error", replies[8])  # valid call still reaches the tool (isError: no scan yet)

    def test_cdp_scan_has_no_state_dir_parameter(self):
        from mcp_server import schemas, tools
        import inspect
        for name, schema in schemas.TOOL_SCHEMAS.items():
            self.assertNotIn("state_dir", schema["inputSchema"]["properties"], name)
            self.assertFalse(schema["inputSchema"]["additionalProperties"], name)
        self.assertNotIn("state_dir", inspect.signature(tools.cdp_scan).parameters)


@unittest.skipUnless(have_git(), "needs git")
class GcDryRunTest(TmpCase):
    """I3: `gc --dry-run` wrote pins and `touch_seq`."""

    def test_dry_run_leaves_the_store_file_byte_identical(self):
        import hashlib
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        first = repo.head()
        L.commit_series(repo, "src/main/java/com/example/svc/Base.java", 1)
        cdp.scan()
        db = cdp.home / "index.db"
        digest = lambda: hashlib.sha256(db.read_bytes()).hexdigest()
        before = digest()
        proc = cdp.run("gc", "--dry-run", "--pin", first)
        self.assertIn("gc        keeping", proc.stdout)
        self.assertEqual(digest(), before)
        self.assertFalse(any(p.stat().st_size for p in cdp.home.glob("index.db-wal")))
        # the pin was only reported, not written: a real gc still drops the unpinned first snapshot
        cdp.run("gc")
        backend, _ = cdp.open()
        try:
            self.assertEqual([s["commit_sha"] for s in backend.list_snapshots()], [repo.head()])
        finally:
            backend.close()


@unittest.skipUnless(have_git(), "needs git")
class RepoStaysCleanTest(TmpCase):
    """J5: CDP wrote into the repo and accepted a `CDP_HOME` inside it."""

    def test_git_status_clean_after_scan_query_and_docs(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.run("query", "stats")
        cdp.run("docs")
        self.assertEqual(repo.git("status", "--porcelain", "--ignored"), "")
        self.assertTrue((repo.path / ".git" / "cdp-identity").exists())  # inside .git, untracked, stays

    def test_cdp_home_inside_the_repo_is_refused_and_writes_nothing(self):
        repo = L.java_inheritance(self.tmp)
        for inside in (repo.path / ".cdp-home", repo.path / "src" / "h", repo.path):
            proc = self.cli("scan", "--repo", str(repo.path), "--quiet", env={"CDP_HOME": str(inside)})
            self.assertNotEqual(proc.returncode, 0, inside)
            self.assertIn("inside the repository", proc.stdout + proc.stderr)
            proc = self.cli("scan", "--repo", str(repo.path), "--quiet", "--state-dir", str(inside))
            self.assertNotEqual(proc.returncode, 0, inside)
        self.assertEqual(repo.git("status", "--porcelain"), "")
        self.assertFalse((repo.path / ".cdp-home").exists())

    def test_subfolder_scan_also_refuses_a_home_in_the_git_root(self):
        repo = L.subfolder_module(self.tmp)
        proc = self.cli("scan", "--repo", str(repo.path / "sql-pool"), "--quiet",
                        env={"CDP_HOME": str(repo.path / "catalog" / "h")})
        self.assertNotEqual(proc.returncode, 0)


@unittest.skipUnless(have_git(), "needs git")
class SymlinkAndSizeTest(TmpCase):
    """B14: links out of the repo were indexed as repo files; files over 2 MB vanished silently."""

    def layout(self):
        repo = L.new_repo(self.tmp)
        outside = self.tmp / "outside_secret.py"
        outside.write_text("def outside_secret():\n    return 'leaked'\n")
        repo.write("pkg/real.py", "def real_function():\n    return 1\n")
        (repo.path / "pkg" / "ext.py").symlink_to(outside)               # file link out of the repo
        (repo.path / "pkg" / "linkdir").symlink_to(self.tmp)             # dir link out of the repo
        (repo.path / "pkg" / "alias.py").symlink_to("real.py")           # link inside the repo
        repo.write("pkg/big.py", "def big_head():\n    return 0\n" + "# pad\n" * 400_000
                   + "def big_tail():\n    return 1\n")
        repo.commit("initial")
        return repo

    def test_outside_links_are_not_indexed_and_skips_are_listed(self):
        repo = self.layout()
        self.assertGreater((repo.path / "pkg" / "big.py").stat().st_size, 2_000_000)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        backend, store = cdp.open()
        try:
            files = {f["path"] for f in store.inventory["files"]}
            fqns = {d["fqn"] for d in store.extraction["defines"]}
            skipped = {r["path"]: r for r in store.inventory["skipped"]}
        finally:
            backend.close()
        self.assertNotIn("pkg/ext.py", files)
        self.assertNotIn("pkg/linkdir", files)
        self.assertFalse([f for f in fqns if "outside_secret" in f])
        self.assertIn("pkg/real.py", files)
        self.assertEqual(skipped["pkg/ext.py"]["reason"], "symlink_outside_repo")
        self.assertEqual(skipped["pkg/linkdir"]["reason"], "symlink_outside_repo")
        self.assertEqual(skipped["pkg/big.py"]["reason"], "too_large")
        self.assertNotIn("pkg/alias.py", skipped)
        text = cdp.run("query", "coverage").stdout
        for path in ("pkg/ext.py", "pkg/big.py"):
            self.assertIn("skipped:    %s" % path, text)

    def test_a_claim_cited_through_an_outside_link_is_not_verified(self):
        from cdp.verify import FileCache
        repo = self.layout()
        self.assertEqual(FileCache(repo.path).lines("pkg/ext.py"), [])
        self.assertTrue(FileCache(repo.path).lines("pkg/real.py"))

    def test_ordinary_repo_inventory_has_no_skipped_key(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        backend, store = cdp.open()
        try:
            self.assertNotIn("skipped", store.inventory)
        finally:
            backend.close()


if __name__ == "__main__":
    unittest.main()
