"""P1: the right snapshot answers (A1-A9, A12, A13, A15, A16), on real temp git layouts.

Each test names the defect it pins. Together they cover the stress cases FIXPLAN asks for:
rebase, shallow clone, detached HEAD, two concurrent worktrees, and a dirty tree over a clean
HEAD snapshot."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_repo

import repo_layouts as L
from repo_layouts import Cdp
from test_layouts import BASE, CHILD, claim

from cdp import hook as hook_mod, snapshot as snapshot_mod
from cdp.session import Paths, route_path
from cdp.store import registry

ALPHA = "a/src/main/java/com/example/a/Alpha.java"
BETA = "b/src/main/java/com/example/b/Beta.java"


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def stats(self, cdp, *extra):
        return cdp.query_json("stats", *extra)["as_of"]

    def status(self, cdp):
        return json.loads(cdp.run("status", "--json").stdout)


@L.needs_git
class WhichSnapshotAnswersTest(Case):
    def test_a1_a_commit_without_a_scan_answers_from_the_parent_and_says_so(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        parent = repo.head()
        L.commit_series(repo, BASE, 1)
        as_of = self.stats(cdp)
        self.assertEqual((as_of["commit"], as_of["behind"], as_of["head"]), (parent, 1, repo.head()))
        self.assertIn("STALE: 1 commit(s) behind", cdp.run("query", "stats").stdout)

    def test_a1_switching_branch_never_answers_from_the_old_branch(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        repo.git("checkout", "-q", "-b", "other")
        L.commit_series(repo, BASE, 1)
        cdp.scan()  # the only snapshot is of `other`'s tip
        repo.git("checkout", "-q", "main")
        proc = cdp.run("query", "stats", check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("scan needed", proc.stderr)
        self.assertEqual(cdp.run("status", check=False).returncode, 2)

    def test_a13_a_reverted_dirty_scan_is_not_served_and_status_equals_head(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        repo.write(ALPHA, repo.read(ALPHA).replace("go()", "dirtyB()"))
        cdp.scan()
        self.assertIn("dirtyB", cdp.run("query", "symbol", "dirtyB").stdout)
        repo.git("checkout", "--", ALPHA)
        self.assertNotIn("com.example.a.Alpha#dirtyB", cdp.run("query", "symbol", "dirtyB", check=False).stdout)
        self.assertEqual(self.status(cdp)["head"], repo.head())

    def test_a9_status_shows_the_new_head_and_behind_after_a_commit(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 2)
        status = self.status(cdp)
        self.assertEqual((status["behind"], status["git_head"]), (2, repo.head()))
        self.assertIn("behind    2 commit(s)", cdp.run("status").stdout)

    def test_a9_prompts_and_run_refuse_a_stale_index_with_the_remedy(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 1)
        for args in (("prompts",), ("collect",), ("run", "--wave-all", "--runner-cmd", "true")):
            proc = cdp.run(*args, check=False)
            self.assertEqual(proc.returncode, 2, args)
            self.assertIn("1 commit(s) behind HEAD", proc.stderr)
            self.assertIn("cdp refresh", proc.stderr)

    def test_a9_a_patch_from_another_snapshots_run_is_rejected_with_the_reason(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        first_run = "cdp-" + repo.head()[:12]
        L.commit_series(repo, BASE, 1)
        cdp.scan()  # a new snapshot with its own run
        cdp.run("prompts")
        backend, store = cdp.open()
        node = store.partition["scopes"][0]["node"]
        inbox = backend._inbox_dir()
        backend.close()
        patch = {"schema_version": "1.0.0", "node": node, "run_id": first_run, "status": "complete",
                 "claims": [claim("t.stale", "com.example.svc.Child")], "unknowns": []}
        (inbox / (node.replace("/", "__") + ".json")).write_text(json.dumps(patch))
        out = cdp.run("collect").stdout
        self.assertIn("rejected 1", out)
        self.assertIn("the patch describes another snapshot", out)
        self.assertEqual(L.model_claim_ids(cdp.open()[0]), [])
        self.assertTrue((inbox / "rejected").is_dir())

    def test_a15_adding_or_changing_the_remote_keeps_the_snapshots(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        repo.git("remote", "add", "origin", "https://example.invalid/team/svc.git")
        self.assertEqual(self.stats(cdp)["behind"], 0)
        repo.git("remote", "set-url", "origin", "https://example.invalid/other/place.git")
        self.assertEqual(self.status(cdp)["head"], repo.head())

    def test_a15_a_lost_marker_still_finds_the_old_identity_by_root_commit(self):
        """The root-commit alias: with no remote to name it, a repo that lost `.git/cdp-identity`
        is still the repo the store already knows (not a fresh UUID with no snapshots)."""
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        first = json.loads(cdp.run("status", "--json").stdout)["identity"]
        (repo.path / ".git" / "cdp-identity").unlink()
        with mock.patch.dict(os.environ, {"CDP_HOME": str(cdp.home)}):
            self.assertEqual(registry.repo_identity(repo.path), first)
        self.assertEqual(self.status(cdp)["identity"], first)

    def test_a15_an_unscanned_repo_is_told_what_is_scanned_by_path_not_by_uuid(self):
        scanned = L.java_inheritance(self.tmp, "scanned")
        cdp = Cdp(self.tmp, scanned.path)
        cdp.scan()
        other = L.new_repo(self.tmp, "other")
        other.write("README.md", "an unrelated history\n")
        other.commit("start")
        out = Cdp(self.tmp, other.path, home=cdp.home).run("query", "stats", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn(str(scanned.path.resolve()), out.stderr + out.stdout)
        self.assertNotRegex(out.stderr + out.stdout, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}")

    def test_a15_two_clones_of_one_origin_share_an_identity_for_good(self):
        repo = L.java_inheritance(self.tmp)
        repo.git("remote", "add", "origin", "https://example.invalid/team/svc.git")
        clone = self.tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(repo.path), str(clone)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(clone), "remote", "set-url", "origin",
                        "https://example.invalid/team/svc.git"], check=True)
        self.assertEqual(registry.repo_identity(clone), registry.repo_identity(repo.path))


@L.needs_git
class AnswersCarryTheirFreshnessTest(Case):
    def test_a7_citations_of_a_file_a_later_commit_touched_are_flagged(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, CHILD, 1)
        result = cdp.query_json("symbol", "inherited")
        use = result["found"][0]["used_by"][0]
        self.assertTrue(use["changed_since"])
        self.assertEqual(result["as_of"]["changed_since"], [CHILD])
        self.assertIn("cited files changed since: " + CHILD, cdp.run("query", "symbol", "inherited").stdout)

    def test_a7_a_citation_of_an_untouched_file_is_not_flagged(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 1)  # Base moves; the use site in Child does not
        use = cdp.query_json("symbol", "inherited")["found"][0]["used_by"][0]
        self.assertNotIn("changed_since", use)

    def test_a7_a_dirty_tree_over_a_clean_head_snapshot_answers_with_a_dirty_marker(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.dirty(repo, BASE, "\n// wip\n")
        as_of = self.stats(cdp)
        self.assertEqual((as_of["behind"], as_of["dirty_files"], as_of["snapshot_uncommitted"]),
                         (0, [BASE], False))
        self.assertIn("UNCOMMITTED changes not in this index: " + BASE, cdp.run("query", "stats").stdout)
        self.assertEqual(self.status(cdp)["dirty_files"], [BASE])

    def test_a7_a_dirty_scan_is_labelled_as_including_the_uncommitted_files_until_the_tree_moves_on(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()  # a clean snapshot of HEAD to fall back to
        L.dirty(repo, BASE, "\n// wip\n")
        cdp.scan()
        text = cdp.run("query", "stats").stdout
        self.assertIn("as of repo@%s+uncommitted" % repo.head()[:12], text)
        self.assertIn("index INCLUDES uncommitted changes (based on commit %s): %s" % (repo.head()[:12], BASE), text)
        self.assertNotIn("not in this index", text)
        self.assertIn("included in this index", cdp.run("status").stdout)
        self.assertTrue(self.status(cdp)["snapshot_uncommitted"])
        L.dirty(repo, BASE, "// more\n")  # the files changed after the scan
        self.assertIn("UNCOMMITTED changes not in this index: " + BASE, cdp.run("query", "stats").stdout)

    def test_a7_a_clean_current_answer_carries_no_caveat(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        as_of = self.stats(cdp)
        self.assertEqual((as_of["behind"], as_of["dirty_files"], as_of["changed_files"]), (0, [], []))
        self.assertNotIn("STALE", cdp.run("query", "stats").stdout)

    def test_a7_the_mcp_tool_carries_the_same_fields(self):
        from mcp_server import tools

        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 1)
        with mock.patch.dict(os.environ, {"CDP_HOME": str(cdp.home)}):
            as_of = tools.cdp_query(str(repo.path), "stats")["as_of"]
            status = tools.cdp_status(str(repo.path))
        self.assertEqual((as_of["behind"], as_of["identity"]), (1, registry.repo_identity(repo.path)))
        self.assertEqual((status["behind"], status["git_head"]), (1, repo.head()))


@L.needs_git
class IdentityAndRoutingTest(Case):
    def test_a2_a_file_in_a_scanned_subfolder_is_answered_by_that_identity_and_says_so(self):
        repo = L.subfolder_module(self.tmp)
        root = Cdp(self.tmp, repo.path)
        sub = Cdp(self.tmp, repo.path / "sql-pool", home=root.home)
        root.scan()
        sub.scan()
        pool = "sql-pool/src/main/java/com/example/pool/Pool.java"
        result = root.query_json("file", pool)
        self.assertTrue(result["as_of"]["identity"].endswith("#sql-pool"))
        self.assertIn("answered from", result["as_of"]["routed"])
        self.assertEqual(result["found"][0]["path"], "src/main/java/com/example/pool/Pool.java")
        # a file outside the subfolder still goes to the root's own index
        other = root.query_json("file", "catalog/src/main/java/com/example/catalog/Catalog.java")
        self.assertFalse(other["as_of"]["identity"].endswith("#sql-pool"))
        self.assertNotIn("routed", other["as_of"])

    def test_a2_the_mcp_tool_routes_the_same_way(self):
        from mcp_server import tools

        repo = L.subfolder_module(self.tmp)
        root = Cdp(self.tmp, repo.path)
        sub = Cdp(self.tmp, repo.path / "sql-pool", home=root.home)
        root.scan()
        sub.scan()
        with mock.patch.dict(os.environ, {"CDP_HOME": str(root.home)}):
            result = tools.cdp_query(str(repo.path), "file", "sql-pool/src/main/java/com/example/pool/Pool.java")
        self.assertTrue(result["as_of"]["identity"].endswith("#sql-pool"))

    def test_a2_route_path_leaves_an_unscanned_or_missing_path_alone(self):
        repo = L.subfolder_module(self.tmp)
        root = Cdp(self.tmp, repo.path)
        root.scan()
        paths = Paths(repo.path, root.home)
        self.assertEqual(route_path(paths, "no/such/file.java")[2], None)
        self.assertEqual(route_path(paths, "sql-pool/pom.xml")[2], None)  # only the root is scanned

    def test_a8_two_worktrees_never_share_a_work_directory(self):
        repo = L.multi_module(self.tmp)
        wt = L.add_worktree(repo, "feature")
        home = self.tmp / "home"
        main_paths, wt_paths = Paths(repo.path, home), Paths(wt.path, home)
        self.assertEqual(main_paths.repo_id, wt_paths.repo_id)  # one identity, two checkouts
        self.assertNotEqual(main_paths.work, wt_paths.work)
        main, feat = Cdp(self.tmp, repo.path, home=home), Cdp(self.tmp, wt.path, home=home)
        main.scan()
        feat.scan()
        main.run("prompts")
        self.assertTrue(list((main_paths.work / "prompts").glob("*.md")))
        self.assertFalse((wt_paths.work / "prompts").exists())


@L.needs_git
class RefreshBuildsOnTheRightSnapshotTest(Case):
    def test_a6_after_a_branch_switch_only_an_ancestors_claims_are_carried(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.main", "com.example.svc.Child")])
        repo.git("checkout", "-q", "-b", "other")
        L.commit_series(repo, BASE, 1)
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.other", "com.example.svc.Base")])
        repo.git("checkout", "-q", "main")
        L.commit_series(repo, CHILD, 1)
        cdp.refresh()
        self.assertEqual(L.model_claim_ids(cdp.open()[0]), ["t.main"])
        live = {c["id"] for c in cdp.open()[0].read_artifact("state")["claims"]}
        self.assertIn("t.main", live)
        self.assertNotIn("t.other", live)

    def test_a12_a_dirty_scan_never_becomes_the_base_of_a_refresh(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        repo.write(ALPHA, repo.read(ALPHA).replace("go()", "dirtyB()"))
        cdp.scan()
        cdp.inject_model_patch("root/a", [claim("t.dirty", "com.example.a.Alpha", file=ALPHA, line=3,
                                                anchor="public class Alpha {")])  # lands on the dirty snapshot
        repo.git("checkout", "--", ALPHA)
        repo.write(BETA, repo.read(BETA).replace("go()", "go2()"))
        repo.commit("module b only")
        cdp.refresh()
        self.assertEqual(L.model_claim_ids(cdp.open()[0]), [])
        self.assertNotIn("dirtyB", json.dumps(cdp.open()[0].read_artifact("extract")))

    def test_a4_the_session_hook_in_a_worktree_reports_the_worktrees_commit(self):
        repo = L.multi_module(self.tmp)
        wt = L.add_worktree(repo, "feature")
        main = Cdp(self.tmp, repo.path)
        main.scan()
        L.commit_series(wt, ALPHA, 1)
        with mock.patch.dict(os.environ, {"CDP_HOME": str(main.home)}):
            message = hook_mod.session_start({"cwd": str(wt.path)})
        self.assertIn("ready: commit %s" % wt.head()[:12], message)
        self.assertNotIn("refresh failed", message)


@L.needs_git
class SessionStartReportsFailuresTest(Case):
    def test_a5_a_refresh_that_fails_is_reported_with_its_reason_and_how_far_behind(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 1)
        L.dirty(repo, CHILD, "\n// wip\n")  # a dirty tree cannot be refreshed
        with mock.patch.dict(os.environ, {"CDP_HOME": str(cdp.home)}):
            message = hook_mod.session_start({"cwd": str(repo.path)})
        self.assertIn("refresh failed: refresh requires a clean working tree", message)
        self.assertIn("1 commit(s) behind HEAD %s" % repo.head()[:12], message)
        self.assertNotIn("is ready", message)

    def test_a5_a_healthy_refresh_says_ready_at_the_current_commit(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 1)
        with mock.patch.dict(os.environ, {"CDP_HOME": str(cdp.home)}):
            message = hook_mod.session_start({"cwd": str(repo.path)})
        self.assertIn("ready: commit %s" % repo.head()[:12], message)

    def test_a5_an_unanswerable_tree_says_scan_needed_not_ready(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        repo.git("checkout", "-q", "-b", "other")
        L.commit_series(repo, BASE, 1)
        cdp.scan()
        repo.git("checkout", "-q", "main")
        with mock.patch.dict(os.environ, {"CDP_HOME": str(cdp.home)}):
            message = hook_mod.session_start({"cwd": str(repo.path)})
        self.assertIn("cannot answer for this tree", message)
        self.assertNotIn("ready", message)


@L.needs_git
class AnswersAndPatchesOnADirtyTreeTest(Case):
    def answer(self, cdp, node, file, line, check=True):
        return cdp.run("answer", node, "--subject", "com.example.svc.Child", "--kind", "naming",
                       "--claim", "A human states a fact about Child here.", "--anchor", "%s:%d" % (file, line),
                       check=check)

    def node(self, cdp):
        backend, store = cdp.open()
        try:
            return store.partition["scopes"][0]["node"]
        finally:
            backend.close()

    def test_a16_an_answer_citing_a_dirty_file_is_rejected_naming_it(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.dirty(repo, CHILD, "\n// wip\n")
        proc = self.answer(cdp, self.node(cdp), CHILD, 5, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn(CHILD, proc.stderr)
        self.assertIn("uncommitted changes", proc.stderr)
        self.assertEqual(L.model_claim_ids(cdp.open()[0]), [])

    def test_a16_an_answer_citing_a_clean_file_lands_on_the_head_snapshot_and_survives_the_next_commit(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.dirty(repo, CHILD, "\n// wip\n")  # elsewhere in the tree
        node = self.node(cdp)
        self.answer(cdp, node, BASE, 4)
        row = cdp.answering_snapshot()
        self.assertEqual((row["commit_sha"], row["ephemeral"]), (repo.head(), False))
        repo.git("checkout", "--", CHILD)
        L.commit_series(repo, BASE, 1)
        cdp.refresh()
        humans = [c for c in cdp.open()[0].read_artifact("state")["claims"] if c.get("author_kind") == "human"]
        self.assertEqual(len(humans), 1)

    def test_a16_collect_rejects_a_patch_citing_a_dirty_file_and_takes_one_citing_clean_files(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.run("prompts")
        node = self.node(cdp)
        backend, _ = cdp.open()
        inbox = backend._inbox_dir()
        backend.close()
        run_id = "cdp-" + repo.head()[:12]
        L.dirty(repo, CHILD, "\n// wip\n")
        dirty_patch = {"schema_version": "1.0.0", "node": node, "run_id": run_id, "status": "complete",
                       "claims": [claim("t.dirty", "com.example.svc.Child")], "unknowns": []}
        (inbox / (node.replace("/", "__") + ".json")).write_text(json.dumps(dirty_patch))
        out = cdp.run("collect").stdout
        self.assertIn("rejected 1", out)
        self.assertIn("uncommitted changes", out)
        clean_patch = dict(dirty_patch, claims=[claim("t.clean", "com.example.svc.Base", file=BASE, line=4,
                                                      anchor="protected int inherited() {")])
        (inbox / (node.replace("/", "__") + ".json")).write_text(json.dumps(clean_patch))
        self.assertIn("accepted  1", cdp.run("collect").stdout)
        self.assertEqual(L.model_claim_ids(cdp.open()[0]), ["t.clean"])


@L.needs_git
class StressCasesTest(Case):
    def test_rebase_answers_from_the_common_base_never_the_rebased_away_tip(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()  # base
        base = repo.head()
        repo.git("checkout", "-q", "-b", "feature")
        L.commit_series(repo, BASE, 2)
        old_tip = repo.head()
        cdp.scan()
        repo.git("checkout", "-q", "main")
        repo.write("main_only.txt", "x\n")
        repo.commit("main moves")
        repo.git("checkout", "-q", "feature")
        repo.git("rebase", "-q", "main")
        self.assertNotEqual(repo.head(), old_tip)
        as_of = self.stats(cdp)
        self.assertEqual(as_of["commit"], base)  # not old_tip: it is no longer reachable
        self.assertEqual(as_of["behind"], 3)
        cdp.refresh()
        self.assertEqual(self.stats(cdp)["behind"], 0)
        self.assertEqual(L.check_answering_snapshot(cdp), [])

    def test_shallow_clone_whose_history_does_not_reach_the_index_says_scan_needed(self):
        repo = L.java_inheritance(self.tmp)
        url = "https://example.invalid/team/svc.git"
        repo.git("remote", "add", "origin", url)
        home = self.tmp / "home"
        Cdp(self.tmp, repo.path, home=home).scan()
        L.commit_series(repo, BASE, 3)
        clone = self.tmp / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://%s" % repo.path, str(clone)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(clone), "remote", "set-url", "origin", url], check=True)
        self.assertEqual(registry.repo_identity(clone), registry.repo_identity(repo.path))
        shallow = Cdp(self.tmp, clone, home=home)
        proc = shallow.run("query", "stats", check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("scan needed", proc.stderr)
        shallow.scan()
        self.assertEqual(self.stats(shallow)["behind"], 0)

    def test_detached_head_answers_from_its_own_or_an_ancestors_snapshot(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        first = repo.head()
        L.commit_series(repo, BASE, 2)
        second = repo.head()
        repo.git("checkout", "-q", "--detach", "HEAD~1")
        as_of = self.stats(cdp)
        self.assertEqual((as_of["commit"], as_of["behind"]), (first, 1))
        cdp.scan()
        self.assertEqual(self.stats(cdp)["behind"], 0)
        repo.git("checkout", "-q", "--detach", first)
        self.assertEqual(self.stats(cdp)["commit"], first)
        repo.git("checkout", "-q", "main")
        self.assertEqual(self.stats(cdp)["commit"], repo.git("rev-parse", "HEAD~1"))
        self.assertEqual(repo.head(), second)

    def test_two_worktrees_queried_at_the_same_time_each_see_only_their_own_branch(self):
        repo = L.multi_module(self.tmp)
        wt = L.add_worktree(repo, "feature")
        main = Cdp(self.tmp, repo.path)
        feat = Cdp(self.tmp, wt.path, home=main.home)
        main.scan()
        L.commit_series(wt, ALPHA, 1)
        feat.scan()
        L.commit_series(repo, BETA, 1)
        wanted = {id(main): repo.git("rev-parse", "HEAD~1"), id(feat): wt.head()}
        seen, errors = [], []

        def ask(who):
            try:
                for _ in range(3):
                    seen.append((id(who), who.query_json("stats")["as_of"]["commit"]))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=ask, args=(who,)) for who in (main, feat, main, feat)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(seen), 12)
        self.assertTrue(all(wanted[who] == commit for who, commit in seen), seen)

    def test_a_subfolder_scan_ignores_a_sibling_modules_uncommitted_edit(self):
        repo = L.subfolder_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path / "sql-pool")
        cdp.scan()
        L.dirty(repo, "catalog/src/main/java/com/example/catalog/Catalog.java", "\n// wip\n")
        as_of = self.stats(cdp)
        self.assertEqual((as_of["dirty_files"], as_of["behind"]), ([], 0))
        self.assertEqual(snapshot_mod.is_dirty(repo.path / "sql-pool"), False)
        self.assertEqual(snapshot_mod.is_dirty(repo.path), True)


class SharedRuleUnitTest(unittest.TestCase):
    def rows(self, *shas, ephemeral=()):
        return [{"id": i, "repo_id": "r", "commit_sha": s, "ephemeral": s in ephemeral}
                for i, s in enumerate(shas, 1)]

    @L.needs_git
    def test_exact_then_nearest_ancestor_then_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = L.java_inheritance(Path(tmp))
            c0 = repo.head()
            L.commit_series(repo, BASE, 2)
            c1, c2 = repo.git("rev-parse", "HEAD~1"), repo.head()
            pick = lambda *shas: snapshot_mod.choose_snapshot(repo.path, "r", self.rows(*shas))
            self.assertEqual((pick(c0, c2).row["commit_sha"], pick(c0, c2).behind), (c2, 0))
            self.assertEqual((pick(c0, c1).row["commit_sha"], pick(c0, c1).behind), (c1, 1))
            self.assertEqual((pick(c0).row["commit_sha"], pick(c0).behind), (c0, 2))
            self.assertTrue(pick("f" * 40).scan_needed)
            self.assertTrue(snapshot_mod.choose_snapshot(repo.path, "other", self.rows(c0)).scan_needed)

    @L.needs_git
    def test_a_dirty_snapshot_is_used_only_for_the_tree_it_was_taken_of(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = L.java_inheritance(Path(tmp))
            head = repo.head()
            L.dirty(repo, BASE, "\n// wip\n")
            sha, _ = snapshot_mod.current_sha(repo.path, head)
            mine = snapshot_mod.choose_snapshot(repo.path, "r", self.rows(head, sha, ephemeral=(sha,)))
            self.assertEqual((mine.row["commit_sha"], mine.exact), (sha, True))
            durable = snapshot_mod.choose_snapshot(repo.path, "r", self.rows(head, sha, ephemeral=(sha,)), durable=True)
            self.assertEqual(durable.row["commit_sha"], head)
            stranger = head + "+dirty:0123456789abcdef"
            other = snapshot_mod.choose_snapshot(repo.path, "r", self.rows(head, stranger, ephemeral=(stranger,)))
            self.assertEqual((other.row["commit_sha"], other.dirty_files), (head, [BASE]))


if __name__ == "__main__":
    unittest.main()


@L.needs_git
class ScanExcludesPersistTest(Case):
    def excluded(self, cdp):
        inv = cdp.artifacts(("inventory",))["inventory"]
        return inv["excluded"]["count"], [f["path"] for f in inv["files"]]

    def test_a14_scan_exclude_survives_every_refresh(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan("--exclude", "b")
        before, files = self.excluded(cdp)
        self.assertGreater(before, 0)
        self.assertFalse([f for f in files if f.startswith("b/")])
        for _ in range(2):  # the carried list must itself be carried again
            L.commit_series(repo, ALPHA, 1)
            cdp.refresh()
            count, files = self.excluded(cdp)
            self.assertEqual(count, before)
            self.assertFalse([f for f in files if f.startswith("b/")], "refresh re-included an excluded file")
        manifest = cdp.artifacts(("manifest",))["manifest"]
        self.assertEqual(manifest.get("excludes"), ["b"])


@L.needs_git
class LinkAndDiffUseTheSharedRuleTest(Case):
    def test_link_scan_inputs_are_the_snapshot_that_answers_for_each_repo(self):
        from cdp.link import snapshots_from_store
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        base = repo.head()
        repo.git("checkout", "-q", "-b", "feat")
        L.commit_series(repo, BASE, 1)
        cdp.scan()                       # newest-touched snapshot is now another branch's
        repo.git("checkout", "-q", "-")
        backend, _ = cdp.open()
        try:
            [snap] = snapshots_from_store(backend)
        finally:
            backend.close()
        self.assertEqual(snap["head"], base)

    def test_diff_defaults_to_this_repos_snapshot_not_the_newest_in_the_store(self):
        repo = L.java_inheritance(self.tmp, "one")
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        other = L.new_repo(self.tmp, "two")
        other.write("README.md", "unrelated\n")
        other.commit("start")
        Cdp(self.tmp, other.path, home=cdp.home).scan()   # now the store-wide newest snapshot
        out = cdp.run("diff", "--old-sha", repo.head(), "--json")
        self.assertEqual(json.loads(out.stdout)["claims"]["added"], [])
