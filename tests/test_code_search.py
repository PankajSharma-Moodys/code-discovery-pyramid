"""Method bodies (ANNOTATIONS_PLAN P12): the `code` artifact, `search`'s `code` bucket, and the
per-member calls / throws / literal count in `file` and `symbol`."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import have_git

from cdp.cli import main
from cdp.codeindex import count_literals, owner_of
from test_hook import _OwnHome
from test_refresh import _commit_all

SERVICE = """package a.svc;

import java.io.IOException;

// TODO remember the Zebra-Policy before shipping
public class OrderService {
    private static final String TABLE = "orders";

    public String load(Long id) throws IOException, IllegalStateException {
        log.info("Loading order {}", id);
        String sql = "SELECT * FROM orders WHERE id = ?";
        return repo.find(sql, id).toString();
    }
    // spacer-note between members

    public void drop() {
        repo.purge("old");   // Quokka cleanup
    }
}
"""

OTHER = """package a.svc;

public class Other {
    public int one() { return 1; }
}
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue()


@unittest.skipUnless(have_git(), "needs a real git repository")
class CodeSearchTest(_OwnHome, unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        self.repo = Path(self.tmp.name) / "r"
        self.write("src/main/java/a/svc/OrderService.java", SERVICE)
        self.write("src/main/java/a/svc/Other.java", OTHER)
        self.write("build.gradle", "apply plugin: 'java'\n")
        self.write("README.md", "Zebra-Policy is described here\n")
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        _commit_all(self.repo, "init")
        self.assertEqual(run("scan", "--repo", str(self.repo), "--quiet")[0], 0)

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def q(self, *argv):
        code, out = run("query", *argv, "--repo", str(self.repo), "--json", "--view", "detail")
        self.assertIn(code, (0, 1), out)      # 1 = nothing matched
        return json.loads(out)

    def code_hits(self, text, *extra):
        return self.q("search", text, *extra)["code"]

    def test_a_literal_in_a_method_is_cited_to_the_member(self):
        (hit,) = self.code_hits("FROM orders WHERE")
        self.assertEqual(hit["owner"], "a.svc.OrderService#load")
        self.assertTrue(hit["at"].endswith("OrderService.java:11"), hit["at"])
        self.assertIn("SELECT * FROM orders", hit["text"])

    def test_a_log_message_is_found_case_insensitively(self):
        (hit,) = self.code_hits("loading ORDER")
        self.assertEqual(hit["owner"], "a.svc.OrderService#load")

    def test_comment_text_is_found(self):
        (inline,) = self.code_hits("quokka")
        self.assertEqual(inline["owner"], "a.svc.OrderService#drop")
        (above,) = self.code_hits("zebra-policy")      # README.md is not source-role: only the .java hit
        self.assertTrue(above["at"].endswith("OrderService.java:5"))

    def test_a_hit_outside_any_member_is_cited_to_the_type(self):
        (hit,) = self.code_hits("zebra")      # above the class: no type to cite, so the file
        self.assertEqual(hit["owner"], "src/main/java/a/svc/OrderService.java")
        (hit,) = self.code_hits("spacer-note")
        self.assertEqual(hit["owner"], "a.svc.OrderService")
        (const,) = self.code_hits('TABLE = "orders"')
        self.assertEqual(const["owner"], "a.svc.OrderService.TABLE")

    def test_text_output_and_not_searched_wording(self):
        code, out = run("query", "search", "purge", "--repo", str(self.repo), "--view", "detail")
        self.assertIn("a.svc.OrderService#drop", out)
        data = self.q("search", "nothing-like-this")
        self.assertNotIn("grep", data["not_searched"])
        self.assertIn("source text", data["searched"])

    def test_counts_are_true_and_the_budget_is_respected(self):
        many = "\n".join('        log.info("needle %d");' % i for i in range(60))
        self.write("src/main/java/a/svc/Many.java",
                   "package a.svc;\npublic class Many {\n    public void go() {\n%s\n    }\n}\n" % many)
        _commit_all(self.repo, "many")
        self.assertEqual(run("scan", "--repo", str(self.repo), "--quiet")[0], 0)
        data = self.q("search", "needle", "--budget", "10")
        self.assertEqual(data["counts"]["code"], 60)
        self.assertEqual(len(data["code"]), 10)
        self.assertEqual(data["elided"], 50)

    def test_file_shows_calls_throws_and_literal_counts(self):
        (entry,) = self.q("file", "OrderService.java")["found"]
        load = next(d for d in entry["defines"] if d["fqn"] == "a.svc.OrderService#load")
        self.assertEqual(load["throws"], ["IOException", "IllegalStateException"])
        self.assertEqual(load["literals"], 2)
        # `log`/`repo` are declared nowhere: their calls are not credited to OrderService (#info, #find)
        self.assertFalse([c for c in load.get("calls", []) if c.startswith("OrderService#")], load.get("calls"))
        code, out = run("query", "file", "OrderService.java", "--repo", str(self.repo), "--view", "detail")
        self.assertIn("throws IOException, IllegalStateException", out)
        self.assertIn("2 string literal(s)", out)

    def test_symbol_shows_calls_throws_and_literal_counts(self):
        (entry,) = self.q("symbol", "a.svc.OrderService#load")["found"]
        (body,) = entry["body"]
        self.assertEqual(body["literals"], 2)
        self.assertIn("IllegalStateException", body["throws"])

    def test_edited_body_deleted_method_and_renamed_file_across_refresh(self):
        self.write("src/main/java/a/svc/OrderService.java",
                   SERVICE.replace("FROM orders WHERE", "FROM carts WHERE")
                          .replace('        repo.purge("old");   // Quokka cleanup\n', ""))
        subprocess.run(["git", "-C", str(self.repo), "mv", "src/main/java/a/svc/Other.java",
                        "src/main/java/a/svc/Renamed.java"], check=True)
        _commit_all(self.repo, "edit, delete, rename")
        self.assertEqual(run("refresh", "--repo", str(self.repo), "--quiet")[0], 0)
        self.assertEqual(self.code_hits("FROM orders WHERE"), [])
        self.assertEqual(self.code_hits("quokka"), [])
        (cart,) = self.code_hits("FROM carts WHERE")
        self.assertEqual(cart["owner"], "a.svc.OrderService#load")
        self.assertTrue(self.code_hits("return 1")[0]["at"].endswith("Renamed.java:4"))
        refreshed = self.artifact()
        # incremental equals full: a fresh scan of the same commit stores the same text
        self.assertEqual(run("scan", "--repo", str(self.repo), "--quiet", "--state-dir",
                             str(Path(self.tmp.name) / "full"))[0], 0)
        code, out = run("query", "search", "carts", "--repo", str(self.repo), "--state-dir",
                        str(Path(self.tmp.name) / "full"), "--json", "--view", "detail")
        self.assertEqual(json.loads(out)["counts"]["code"], 1)
        self.assertEqual(sorted(refreshed["files"]), sorted(self.artifact(Path(self.tmp.name) / "full")["files"]))
        self.assertEqual(refreshed, self.artifact(Path(self.tmp.name) / "full"))

    def artifact(self, state=None):
        from cdp.store import SqliteStore
        backend = SqliteStore((state or self.home) / "index.db")
        try:
            backend.use_latest_snapshot()
            return backend.read_artifact("code")
        finally:
            backend.close()

    def test_dirty_tree_caveat_is_stated_in_as_of(self):
        self.write("src/main/java/a/svc/Other.java", OTHER.replace("return 1", 'return "dirty-marker".length()'))
        data = self.q("search", "return 1")
        self.assertIn("uncommitted edits since the scan", data["as_of"]["code_note"])
        self.assertEqual(run("scan", "--repo", str(self.repo), "--quiet")[0], 0)
        data = self.q("search", "dirty-marker")
        self.assertEqual(data["code"][0]["owner"], "a.svc.Other#one")
        self.assertIn("uncommitted edits included", data["as_of"]["code_note"])
        code, out = run("query", "search", "dirty-marker", "--repo", str(self.repo), "--view", "detail")
        self.assertIn("note: code text is from the working files", out)

    def test_non_source_roles_are_not_in_the_artifact(self):
        files = self.artifact()["files"]
        self.assertEqual(sorted(files), ["src/main/java/a/svc/OrderService.java", "src/main/java/a/svc/Other.java"])


class HelperTest(unittest.TestCase):
    def test_owner_of_prefers_the_innermost_extent_then_the_type(self):
        rows = [(1, 0, "T", "class"), (3, 9, "T#a", "method"), (5, 6, "T#a.inner", "method"),
                (11, 0, "T.X", "constant")]
        self.assertEqual(owner_of(rows, 5), "T#a.inner")
        self.assertEqual(owner_of(rows, 8), "T#a")
        self.assertEqual(owner_of(rows, 10), "T")
        self.assertEqual(owner_of(rows, 11), "T.X")
        self.assertIsNone(owner_of([], 4))

    def test_literal_count_skips_comments_and_char_literals(self):
        text = 'a("x"); // "no"\n/* "no" */ b("y\\"z", \'"\');\n"""\nblock\n"""\n'
        self.assertEqual(count_literals("A.java", text, 1, 5), 3)
        self.assertEqual(count_literals("a.py", text, 1, 5), 0)


if __name__ == "__main__":
    unittest.main()
