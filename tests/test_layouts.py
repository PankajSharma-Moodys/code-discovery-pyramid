"""F2: the invariants of `repo_layouts` on real repo layouts.

`KnownDefectsTest` holds one regression test per defect in DEFECTS.md that these layouts
expose; each comment names its defect IDs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

import repo_layouts as L
from repo_layouts import Cdp, check_answering_snapshot, check_derived_claims_live, check_no_silent_loss, \
    check_refresh_equals_scan

BASE = "src/main/java/com/example/svc/Base.java"
CHILD = "src/main/java/com/example/svc/Child.java"


def claim(cid, subject, file=CHILD, line=5, anchor="public class Child extends Base implements Provisioner {"):
    return {"id": cid, "kind": "naming", "subject": subject, "confidence": "high",
            "statement": "Model statement %s about %s." % (cid, subject),
            "evidence": [{"file": file, "line": line, "anchor": anchor}]}


@L.needs_git
class LayoutCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def solo(self):
        """The service fixture: it has derived claims (entity, route)."""
        repo = L.Repo(make_repo(self.tmp, "solorepo"))
        return repo, Cdp(self.tmp, repo.path)


@L.needs_git
class LayoutBuildersTest(LayoutCase):
    def test_worktree_rebase_rename_and_whitespace_layouts(self):
        repo = L.java_inheritance(self.tmp)
        wt = L.add_worktree(repo, "feature")
        self.assertEqual(wt.branch(), "feature")
        self.assertEqual(wt.git("rev-parse", "--git-common-dir"), str(repo.path / ".git"))
        sha = L.whitespace_only_commit(repo, BASE)
        self.assertTrue(repo.read(BASE).startswith("\n\n\n\n\npackage"))
        L.rename(repo, BASE, "src/main/java/com/example/svc/Root.java")
        self.assertEqual(repo.git("status", "--porcelain"), "")
        self.assertTrue(sha)
        other = L.java_inheritance(self.tmp, "other")
        hist = L.rebased_history(other)
        self.assertNotEqual(hist["old_tip"], hist["new_tip"])
        other.git("merge-base", "--is-ancestor", hist["main_tip"], "HEAD")  # raises if not an ancestor
        self.assertEqual(other.git("rev-parse", "HEAD~2"), hist["main_tip"])

    def test_subfolder_and_multi_module_layouts_scan_as_their_own_modules(self):
        repo = L.subfolder_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path / "sql-pool")
        cdp.scan()
        backend, store = cdp.open()
        try:
            self.assertEqual({f["path"].split("/")[0] for f in store.inventory["files"]}, {"pom.xml", "src"})
        finally:
            backend.close()
        multi = L.multi_module(self.tmp, "multi")
        cdp2 = Cdp(self.tmp, multi.path)
        cdp2.scan()
        backend, store = cdp2.open()
        try:
            self.assertEqual(len(store.partition["scopes"]) >= 2, True)
        finally:
            backend.close()

    def test_java_inheritance_layout_has_the_shapes_the_java_defects_need(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        backend, store = cdp.open()
        try:
            fqns = {d["fqn"] for d in store.extraction["defines"]}
        finally:
            backend.close()
        self.assertIn("com.example.svc.Child", fqns)
        self.assertIn("com.example.svc.Base#inherited", fqns)


@L.needs_git
class CheckersHoldOnWellBehavedHistoriesTest(LayoutCase):
    """Positive controls: today's code keeps these invariants, and must keep them."""

    def refreshed(self, repo, cdp, edit):
        cdp.scan()
        edit(repo)
        cdp.refresh()
        return cdp

    def test_edit_commit_in_a_root_repo(self):
        repo = L.java_inheritance(self.tmp)
        cdp = self.refreshed(repo, Cdp(self.tmp, repo.path),
                             lambda r: L.commit_series(r, BASE, 2))
        self.assertEqual(L.check_all(cdp) + check_refresh_equals_scan(cdp), [])

    def test_rename_commit(self):
        repo = L.java_inheritance(self.tmp)
        cdp = self.refreshed(repo, Cdp(self.tmp, repo.path),
                             lambda r: L.rename(r, BASE, "src/main/java/com/example/svc/Core.java"))
        self.assertEqual(check_refresh_equals_scan(cdp), [])

    def test_commit_in_one_module_of_a_multi_module_repo(self):
        repo = L.multi_module(self.tmp)
        cdp = self.refreshed(repo, Cdp(self.tmp, repo.path),
                             lambda r: L.commit_series(r, "b/src/main/java/com/example/b/Beta.java", 1))
        self.assertEqual(L.check_all(cdp) + check_refresh_equals_scan(cdp), [])

    def test_refresh_after_rebase(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.rebased_history(repo)
        cdp.refresh()
        self.assertEqual(check_answering_snapshot(cdp) + check_refresh_equals_scan(cdp), [])

    def test_dirty_scan_answers_from_a_matching_dirty_snapshot(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.dirty(repo, BASE, "\n// wip\n")
        cdp.scan()
        self.assertEqual(check_answering_snapshot(cdp), [])

    def test_model_claim_survives_a_refresh(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")])
        before = L.model_claim_ids(cdp.open()[0])
        L.commit_series(repo, BASE, 1)
        cdp.refresh()
        self.assertEqual(before, ["t.one"])
        self.assertEqual(check_no_silent_loss(cdp, before), [])


    # A model claim whose file is renamed or edited, across one or two refreshes: the state
    # `refresh` writes is exactly fold(patches), so `verify` and `fold --check` stay green (Cdp
    # asserts that after every command) and the claim is kept, not demoted.
    def _model_repo(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")])
        return repo, cdp

    def _live_model_claims(self, cdp):
        backend, _ = cdp.open()
        try:
            return {c["id"]: c for c in backend.read_artifact("state")["claims"] if c["id"].startswith("t.")}
        finally:
            backend.close()

    def test_refresh_after_renaming_an_anchored_file_keeps_state_derivable(self):
        repo, cdp = self._model_repo()
        L.rename(repo, CHILD, "src/main/java/com/example/svc/Kid.java")
        cdp.refresh()
        self.assertEqual(L.check_fold_green(cdp), [])
        self.assertIn("t.one", self._live_model_claims(cdp))

    def test_refresh_after_editing_an_anchored_file_keeps_state_derivable(self):
        repo, cdp = self._model_repo()
        L.commit_series(repo, CHILD, 1)
        cdp.refresh()
        self.assertEqual(L.check_fold_green(cdp), [])
        claim_row = self._live_model_claims(cdp)["t.one"]
        self.assertIsNone(claim_row["claim_reviewed_at"], "an edited anchored file clears the review")

    def test_two_refreshes_after_a_rename_keep_the_claim(self):
        repo, cdp = self._model_repo()
        L.rename(repo, CHILD, "src/main/java/com/example/svc/Kid.java")
        cdp.refresh()
        L.commit_series(repo, BASE, 1)
        cdp.refresh()  # the claim's own anchor still names Child.java in the log
        self.assertEqual(L.check_fold_green(cdp), [])
        self.assertIn("t.one", self._live_model_claims(cdp))
        self.assertEqual(check_no_silent_loss(cdp), [])


@L.needs_git
class CheckersDetectBreakageTest(LayoutCase):
    """Negative controls: each checker flags a hand-made violation, so the
    defect tests below cannot be passing for the wrong reason."""

    def test_refresh_equals_scan_flags_a_tampered_artifact(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        backend, store = cdp.open()
        ext = store.extraction
        ext["defines"][0]["anchor"]["line"] += 1
        backend.write_artifact("extract", ext)
        backend.close()
        problems = check_refresh_equals_scan(cdp)
        self.assertTrue(any("anchor.line" in p for p in problems), problems)

    def test_no_silent_loss_flags_a_claim_missing_from_state(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")])
        backend, store = cdp.open()
        state = store.state
        state["claims"] = [c for c in state["claims"] if c["id"] != "t.one"]
        backend.write_artifact("state", state)
        backend.close()
        self.assertEqual(len(check_no_silent_loss(cdp)), 1)

    def test_derived_claims_live_flags_a_missing_derived_claim(self):
        _, cdp = self.solo()
        cdp.scan()
        backend, store = cdp.open()
        state = store.state
        state["claims"] = state["claims"][1:]
        backend.write_artifact("state", state)
        backend.close()
        self.assertEqual(len(check_derived_claims_live(cdp)), 1)

    def test_answering_snapshot_flags_a_foreign_branch_and_a_foreign_dirty_tree(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        sibling = repo.head()
        repo.git("checkout", "-q", "-b", "other")
        L.commit_series(repo, BASE, 1)
        repo.git("checkout", "-q", "main")
        L.commit_series(repo, BASE, 1)
        rows = [
            {"commit_sha": repo.git("rev-parse", "other"), "ephemeral": False},
            {"commit_sha": sibling + "+dirty:0123456789abcdef", "ephemeral": True},
        ]
        for row in rows:
            cdp.answering_snapshot = lambda row=row: row
            self.assertEqual(len(check_answering_snapshot(cdp)), 1, row)
        cdp.answering_snapshot = lambda: {"commit_sha": sibling, "ephemeral": False}
        self.assertEqual(check_answering_snapshot(cdp), [])  # a clean ancestor is allowed


@L.needs_git
class KnownDefectsTest(LayoutCase):
    """Each test is the invariant that should hold; the comment names the defects it covers."""

    # A10
    def test_subfolder_refresh_equals_scan(self):
        repo = L.subfolder_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path / "sql-pool")
        cdp.scan()
        L.commit_series(repo, "sql-pool/src/main/java/com/example/pool/Pool.java", 1)
        cdp.refresh()
        self.assertEqual(check_refresh_equals_scan(cdp), [])

    # A11
    def test_whitespace_only_commit_refresh_equals_scan(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.whitespace_only_commit(repo, BASE)
        cdp.refresh()
        self.assertEqual(check_refresh_equals_scan(cdp), [])

    # A12 (dirty facts leak into the next permanent snapshot)
    def test_dirty_scan_does_not_leak_into_the_next_commit(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        a = "a/src/main/java/com/example/a/Alpha.java"
        b = "b/src/main/java/com/example/b/Beta.java"
        cdp.scan()
        repo.write(a, repo.read(a).replace("go()", "dirtyB()"))
        cdp.scan()
        repo.git("checkout", "--", a)
        repo.write(b, repo.read(b).replace("go()", "go2()"))
        repo.commit("module b only")
        cdp.refresh()
        self.assertEqual(check_refresh_equals_scan(cdp), [])

    # A13 (queries ignore the working tree after a revert)
    def test_reverted_dirty_scan_is_not_served(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        a = "a/src/main/java/com/example/a/Alpha.java"
        cdp.scan()
        repo.write(a, repo.read(a).replace("go()", "dirtyB()"))
        cdp.scan()
        repo.git("checkout", "--", a)
        self.assertEqual(check_answering_snapshot(cdp), [])

    # A1, A9 (a commit or branch switch without a scan)
    def test_other_branchs_snapshot_never_answers(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        repo.git("checkout", "-q", "-b", "other")
        L.commit_series(repo, "a/src/main/java/com/example/a/Alpha.java", 1)
        cdp.scan()
        repo.git("checkout", "-q", "main")
        L.commit_series(repo, "b/src/main/java/com/example/b/Beta.java", 1)
        self.assertEqual(check_answering_snapshot(cdp), [])

    # A3 (worktrees share one identity)
    def test_two_worktrees_on_two_branches_see_only_their_own(self):
        repo = L.multi_module(self.tmp)
        wt = L.add_worktree(repo, "feature")
        main, feat = Cdp(self.tmp, repo.path), Cdp(self.tmp, wt.path, home=Cdp(self.tmp, repo.path).home)
        main.scan()
        L.commit_series(wt, "a/src/main/java/com/example/a/Alpha.java", 1)
        feat.scan()
        L.commit_series(repo, "b/src/main/java/com/example/b/Beta.java", 1)
        self.assertEqual(check_answering_snapshot(main) + check_answering_snapshot(feat), [])

    # A4 (refresh refuses in any worktree but the first scanned)
    def test_refresh_in_a_second_worktree(self):
        repo = L.multi_module(self.tmp)
        wt = L.add_worktree(repo, "feature")
        main = Cdp(self.tmp, repo.path)
        feat = Cdp(self.tmp, wt.path, home=main.home)
        main.scan()
        L.commit_series(wt, "a/src/main/java/com/example/a/Alpha.java", 1)
        feat.refresh()
        self.assertEqual(check_answering_snapshot(feat), [])

    # L1 (a model patch for `root` wipes the scan's derived claims)
    def test_root_patch_keeps_derived_claims(self):
        repo, cdp = self.solo()
        cdp.scan()
        cdp.inject_model_patch("root", [claim(
            "t.root", "com.example.solo.OrderResource", file="src/main/java/com/example/solo/OrderResource.java",
            line=1, anchor="package com.example.solo;")])
        self.assertEqual(check_derived_claims_live(cdp), [])

    # L2 (an abandoned scope drops its derived claims)
    def test_abandoned_scope_keeps_derived_claims(self):
        repo, cdp = self.solo()
        cdp.scan()
        cdp.run("run", "--wave-all", "--max-attempts", "1", "--runner-cmd", "false", check=False)
        self.assertEqual(check_derived_claims_live(cdp), [])

    # L3 (each answer replaces every earlier one)
    def test_answers_on_different_subjects_all_stay_live(self):
        repo, cdp = self.solo()
        cdp.scan()
        backend, store = cdp.open()
        node = store.partition["scopes"][0]["node"]
        backend.close()
        ids = []
        for subject in ("OrderResource", "OrderRepository", "Solo.a", "Solo.b", "Solo.c", "Solo.d"):
            proc = cdp.run(
                "answer", node, "--subject", "com.example.solo." + subject, "--kind", "naming",
                "--claim", "A human states a fact about %s here." % subject,
                "--anchor", "src/main/java/com/example/solo/OrderResource.java:1", check=False)
            ids.append(proc.returncode)
        backend, _ = cdp.open()
        humans = [c for c in backend.read_artifact("state")["claims"] if c.get("author_kind") == "human"]
        backend.close()
        self.assertEqual(len(humans), 6, ids)


if __name__ == "__main__":
    unittest.main()
