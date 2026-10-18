"""`query symbol`: each `used_by` row names the member whose body holds the use (`in`).

A diagram cites the line that performs an edge (`at`) and names the caller node; `in` gives the
caller from the file's `defines` extents, so no second query is needed. A use at class or field
level (a field type, an import) has no enclosing member and no `in`.
"""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import Pipeline  # noqa: F401  (sets sys.path)

from cdp.cli import main
from cdp.query import Store, render
from cdp.query.lookup import q_symbol

JAVA_REPO = """\
package a;

public class Repo {
    public void save(String s) {
    }
}
"""

JAVA_SVC = """\
package a;

public class Svc {
    private final Repo repo = new Repo();

    public Svc() {
        new Repo().save("ctor");
    }

    public void run() {
        repo.save("x");
        Runnable r = new Runnable() {
            public void run() {
                repo.save("inner");
            }
        };
    }

    public void other() {
        repo.save("y");
    }
}
"""

PY_MOD = """\
def helper():
    return 1


def outer():
    def inner():
        return helper()
    return inner() + helper()


VALUE = helper()
"""


def _repo(tmp: Path) -> Path:
    files = {"src/main/java/a/Repo.java": JAVA_REPO, "src/main/java/a/Svc.java": JAVA_SVC, "pkg/mod.py": PY_MOD}
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


class CallSitesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = _repo(Path(cls.tmp.name) / "repo")
        cls.state = Path(cls.tmp.name) / "state"
        main(["scan", "--repo", str(cls.repo), "--state-dir", str(cls.state), "--quiet"])
        cls.store = Store(cls.state)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.tmp.cleanup()

    def uses(self, name: str) -> dict:
        found = q_symbol(self.store, name, exact=True)["found"]
        self.assertTrue(found, name)
        return {u["at"].rsplit(":", 1)[-1]: u.get("in") for u in found[0]["used_by"]}

    def test_java_method_body_constructor_and_anonymous_class(self) -> None:
        got = self.uses("a.Repo#save")
        self.assertEqual(got.get("7"), "a.Svc#<init>")
        self.assertEqual(got.get("11"), "a.Svc#run")
        self.assertEqual(got.get("20"), "a.Svc#other")
        # an anonymous class's method is not a define of its own: the use falls to the outer method
        self.assertEqual(got.get("14"), "a.Svc#run")

    def test_field_level_use_has_no_in(self) -> None:
        got = self.uses("a.Repo")
        self.assertIn("4", got)
        self.assertIsNone(got["4"])

    def test_python_innermost_function_wins(self) -> None:
        got = self.uses("pkg.mod#helper")
        self.assertEqual(got.get("7"), "pkg.mod#outer.inner")
        self.assertEqual(got.get("8"), "pkg.mod#outer")
        self.assertIsNone(got.get("11"))   # module level

    def test_json_and_text_views(self) -> None:
        for view, owner in (("detail", "a.Svc#run"), ("compact", "Svc#run")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["query", "symbol", "a.Repo#save", "--exact", "--json", "--view", view,
                      "--repo", str(self.repo), "--state-dir", str(self.state)])
            rows = json.loads(buf.getvalue())["found"][0]["used_by"]
            self.assertIn({"module": rows[0]["module"], "at": "src/main/java/a/Svc.java:11", "in": owner}, rows, view)
        text = render(q_symbol(self.store, "a.Repo#save", exact=True))
        self.assertRegex(text, r"src/main/java/a/Svc\.java:11  in a\.Svc#run\n")
        field = render(q_symbol(self.store, "a.Repo", exact=True))
        self.assertRegex(field, r"src/main/java/a/Svc\.java:4\n")


class HelpColumnsTest(unittest.TestCase):
    def test_commands_column_fits_the_longest_name(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["help"])
        lines = buf.getvalue().split("COMMANDS\n", 1)[1].split("\n\n", 1)[0].splitlines()
        self.assertGreater(len(lines), 3)
        names = [ln.split()[0] for ln in lines]
        starts = {len(ln) - len(ln[2 + len(n):].lstrip()) for ln, n in zip(lines, names)}
        self.assertEqual(starts, {2 + max(map(len, names)) + 1}, lines)


if __name__ == "__main__":
    unittest.main()
