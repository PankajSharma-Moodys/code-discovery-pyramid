import ast
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cdp.runner import FileRunner, SubprocessRunner

STDLIB_ALLOWED = {"__future__", "json", "os", "signal", "subprocess", "time", "dataclasses", "pathlib", "typing"}


class RunnerStdlibOnlyTest(unittest.TestCase):
    """M5.1 acceptance: neither reference runner imports outside stdlib."""

    def test_runner_module_imports_only_stdlib(self):
        import cdp.runner as runner_mod

        tree = ast.parse(Path(runner_mod.__file__).read_text())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertTrue(found, "expected at least one import")
        self.assertEqual(found - STDLIB_ALLOWED, set())


class RunnerConformanceTest(unittest.TestCase):
    """Same two assertions driven against both reference runners -- this is
    what M5.1's 'a conformance test drives both' means in code."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.prompt = self.tmp / "root__scope.md"
        self.prompt.write_text("scope prompt text")
        self.patch = self.tmp / "root__scope.json"

    def _assert_success(self, runner):
        result = runner.run(self.prompt, self.patch)
        self.assertTrue(result.ok, result.error)
        self.assertIsInstance(result.wall_ms, int)
        self.assertGreaterEqual(result.wall_ms, 0)
        self.assertIsNone(result.error)
        self.assertTrue(self.patch.exists())

    def _assert_failure(self, runner):
        result = runner.run(self.prompt, self.patch)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertIsInstance(result.wall_ms, int)

    def test_subprocess_runner_success(self):
        cmd = [sys.executable, "-c",
                "import sys,json; json.dump({'node':'n'}, open(sys.argv[2], 'w'))"]
        self._assert_success(SubprocessRunner(cmd, timeout_s=10))

    def test_subprocess_runner_nonzero_exit_is_failure(self):
        cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
        self._assert_failure(SubprocessRunner(cmd, timeout_s=10))

    def test_subprocess_runner_timeout_is_failure_not_exception(self):
        cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
        self._assert_failure(SubprocessRunner(cmd, timeout_s=0.2))

    def _wrapper_with_slow_child(self):
        """`bash wrapper -> python child` (the shape of cdp-claude-leaf.sh -> claude): the child
        writes the patch after 2.5s; the wrapper does not exec, so it stays the parent."""
        pidfile = self.tmp / "child.pid"
        script = self.tmp / "wrapper.sh"
        script.write_text(
            "#!/bin/bash\n%s -c 'import os,sys,time; open(sys.argv[1],\"w\").write(str(os.getpid())); "
            "time.sleep(2.5); open(sys.argv[2],\"w\").write(\"{}\")' %s \"$2\"\nexit $?\n"
            % (sys.executable, pidfile))
        script.chmod(0o755)
        return script, pidfile

    def test_timeout_kills_the_whole_process_tree_so_no_late_patch_appears(self):
        script, pidfile = self._wrapper_with_slow_child()
        result = SubprocessRunner(["bash", str(script)], timeout_s=1).run(self.prompt, self.patch)
        self.assertFalse(result.ok)
        self.assertIn("timed out", result.error)
        pid = int(pidfile.read_text())
        time.sleep(2.5)  # past the moment the orphan would have written
        self.assertFalse(self.patch.exists(), "an orphaned child wrote its patch after the timeout")
        with self.assertRaises(ProcessLookupError):
            __import__("os").kill(pid, 0)

    def test_keyboard_interrupt_kills_the_tree_too(self):
        script, pidfile = self._wrapper_with_slow_child()
        import os, signal
        self.addCleanup(signal.signal, signal.SIGINT, signal.signal(signal.SIGINT, signal.default_int_handler))
        threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
        with self.assertRaises(KeyboardInterrupt):
            SubprocessRunner(["bash", str(script)], timeout_s=30).run(self.prompt, self.patch)
        pid = int(pidfile.read_text())
        time.sleep(2.5)
        self.assertFalse(self.patch.exists())
        with self.assertRaises(ProcessLookupError):
            __import__("os").kill(pid, 0)

    def test_file_runner_success(self):
        runner = FileRunner(poll_interval_s=0.05, timeout_s=10)
        patch = self.patch

        def writer():
            time.sleep(0.1)
            patch.write_text("{}")

        threading.Thread(target=writer).start()
        self._assert_success(runner)

    def test_file_runner_timeout_is_failure_not_exception(self):
        self._assert_failure(FileRunner(poll_interval_s=0.05, timeout_s=0.2))


if __name__ == "__main__":
    unittest.main()
