"""State-core defects found by an independent review: gc retention, compact vs rollback, hostile
inbox files, scan vs model claims, non-git change detection, archive scoping, empty rollback targets.

Each test reproduces a defect through the CLI, on real temp git repos and a temp CDP_HOME."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import repo_layouts as L
from repo_layouts import Cdp, check_fold_green, check_no_silent_loss
from test_layouts import BASE, CHILD, LayoutCase, claim


def snapshots(cdp):
    backend, _ = cdp.open()
    try:
        return backend.list_snapshots()
    finally:
        backend.close()


def live_ids(cdp):
    backend, _ = cdp.open()
    try:
        return sorted(c["id"] for c in backend.read_artifact("state")["claims"] if c["id"].startswith("t."))
    finally:
        backend.close()


def hot_ids(cdp):
    backend, _ = cdp.open()
    try:
        return sorted(c["id"] for p in backend.load_patches() if p.get("author_kind") != "python"
                      for c in p.get("claims") or [])
    finally:
        backend.close()


@L.needs_git
class GcKeepsOtherCheckoutsTest(LayoutCase):
    def _two_worktrees(self):
        repo = L.java_inheritance(self.tmp)
        wt = L.add_worktree(repo, "feat")
        home = self.tmp / "home"
        main, feat = Cdp(self.tmp, repo.path, home=home), Cdp(self.tmp, wt.path, home=home)
        main.scan()
        L.dirty(wt, BASE, "\n// feature work\n")
        wt.commit("feature")
        feat.scan()
        feat.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")])
        return repo, wt, main, feat

    def test_gc_in_main_keeps_the_other_worktrees_snapshot_and_its_claim(self):
        _, _, main, feat = self._two_worktrees()
        before = len(snapshots(main))
        main.run("gc")
        self.assertEqual(len(snapshots(main)), before)
        self.assertEqual(live_ids(feat), ["t.one"])
        self.assertEqual(check_no_silent_loss(feat), [])

    def test_gc_after_a_branch_switch_keeps_the_branch_that_holds_model_claims(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        repo.git("checkout", "-q", "-b", "other")
        L.dirty(repo, BASE, "\n// other\n")
        repo.commit("other")
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")])
        repo.git("checkout", "-q", "main")
        cdp.run("gc")
        repo.git("checkout", "-q", "other")
        self.assertEqual(live_ids(cdp), ["t.one"])

    def test_dry_run_says_why_each_snapshot_is_kept_and_drop_unreviewed_drops_it(self):
        _, _, main, feat = self._two_worktrees()
        out = main.run("gc", "--dry-run").stdout
        self.assertIn("keep", out)
        self.assertIn("model", out)
        self.assertIn("checkout", out)
        n = len(snapshots(main))
        main.run("gc", "--drop-unreviewed")
        self.assertLess(len(snapshots(main)), n)

    def test_gc_still_drops_an_unreviewed_snapshot_nobody_stands_on(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 1)
        cdp.scan()
        L.commit_series(repo, BASE, 1)
        cdp.scan()
        n = len(snapshots(cdp))
        cdp.run("gc")
        self.assertLess(len(snapshots(cdp)), n)


@L.needs_git
class CompactRollbackTest(LayoutCase):
    def _gens(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")],
                               generation=1, run_id="cdp-aaaaaaaaaaaa")
        cdp.inject_model_patch("root/svc", [claim("t.two", "com.example.svc.Base", file=BASE, line=3,
                                                    anchor="public abstract class Base {")],
                               generation=2, run_id="cdp-bbbbbbbbbbbb")
        return cdp

    def test_compact_after_a_rollback_does_not_archive_the_live_claim(self):
        cdp = self._gens()
        cdp.run("rollback", "--to-run", "cdp-bbbbbbbbbbbb")
        self.assertEqual(live_ids(cdp), ["t.one"])
        cdp.run("compact", "--compact-threshold", "0")
        self.assertEqual(live_ids(cdp), ["t.one"])
        self.assertIn("t.one", hot_ids(cdp))
        cdp.run("rollback", "--undo")
        self.assertEqual(live_ids(cdp), ["t.two"])
        self.assertEqual(check_no_silent_loss(cdp), [])
        self.assertEqual(L.check_fold_green(cdp), [])
        cdp.run("verify", "--full")

    def test_rollback_after_compact_brings_the_archived_generation_back(self):
        cdp = self._gens()
        cdp.run("compact", "--compact-threshold", "0")
        self.assertEqual(live_ids(cdp), ["t.two"])
        cdp.run("rollback", "--to-run", "cdp-bbbbbbbbbbbb")
        self.assertEqual(live_ids(cdp), ["t.one"])
        cdp.run("verify", "--full")
        cdp.run("rollback", "--undo")
        self.assertEqual(live_ids(cdp), ["t.two"])
        cdp.run("verify", "--full")

    def test_compact_aborts_when_the_live_view_would_change(self):
        from cdp.store import sqlite_archive
        cdp = self._gens()
        real = sqlite_archive.superseded_for
        sqlite_archive.superseded_for = lambda patches, exclusions, keep: [0, 1]  # archives the live generation too
        self.addCleanup(setattr, sqlite_archive, "superseded_for", real)
        from cdp.util import CdpError
        backend, _ = cdp.open()
        try:
            with self.assertRaises(CdpError):
                backend.compact(threshold=0)
            self.assertIn("t.two", [c["id"] for p in backend.load_patches() for c in p.get("claims") or []])
        finally:
            backend.close()


@L.needs_git
class HostileInboxTest(LayoutCase):
    def _inbox(self, cdp):
        from cdp.session import paths_for
        return paths_for(cdp.target, cdp.home).work / "patches" / "inbox"

    def test_a_non_object_inbox_file_is_rejected_and_does_not_block_valid_patches(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        inbox = self._inbox(cdp)
        for i, text in enumerate(["[]", "null", "42", '"x"', "true", "{"]):
            (inbox / ("a%d.json" % i)).write_text(text)
        backend, store = cdp.open()
        run_id = store.manifest["run_id"]
        backend.close()
        (inbox / "root__svc.json").write_text(json.dumps({
            "schema_version": "1.0.0", "node": "root/svc", "run_id": run_id, "status": "complete",
            "claims": [claim("t.one", "com.example.svc.Child")], "unknowns": []}))
        proc = cdp.run("collect", check=False)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)  # some rejected, the valid one accepted
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(sorted(p.name for p in inbox.glob("*.json")), [])
        self.assertEqual(len(list((inbox / "rejected").glob("a*.json*"))), 6)
        self.assertIn("accepted  1 patch(es), rejected 6", proc.stdout)
        self.assertEqual(live_ids(cdp), ["t.one"])
        again = cdp.run("collect", check=False)
        self.assertEqual(again.returncode, 0)

    def test_malformed_members_of_an_object_patch_are_rejected_not_crashes(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        inbox = self._inbox(cdp)
        bad = [{"node": "root/svc", "claims": "x"}, {"node": "root/svc", "claims": [1, "a", None]},
               {"node": ["x"], "claims": []}, {"node": "root/svc", "claims": [{"id": "t", "evidence": 5}]},
               {"node": "root/svc", "claims": [{"id": "t", "evidence": [7]}], "unknowns": "x"},
               {"node": "root/svc", "run_id": ["x"], "claims": []}, {"node": "root/svc", "unknowns": [1]}]
        for i, patch in enumerate(bad):
            (inbox / ("b%d.json" % i)).write_text(json.dumps(patch))
        proc = cdp.run("collect", check=False)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)  # all rejected, none accepted
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(sorted(p.name for p in inbox.glob("*.json")), [])


class RunIntakeShapeTest(unittest.TestCase):
    def test_cdp_run_rejects_malformed_patches_instead_of_crashing(self):
        from cdp import supervisor
        from cdp.schema import Validator, schema_path
        from cdp.util import SKILL_ROOT
        from cdp.verify import STRICT
        validator = Validator.load(schema_path(SKILL_ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "n.json"
            for body in ('[]', 'null', '{"node": "n", "claims": "x"}', '{"node": "n", "claims": [1]}',
                         '{"node": "n", "claims": [{"id": "a", "evidence": [3]}]}',
                         '{"node": "n", "claims": [], "unknowns": [[]]}'):
                path.write_text(body)
                state, error, patch = supervisor._classify_returned(path, "n", validator, Path(tmp), STRICT, object())
                self.assertEqual(state, supervisor.INVALID, (body, error))
                self.assertIsNone(patch)


@L.needs_git
class ScanKeepsModelClaimsTest(LayoutCase):
    def _model_repo(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")])
        return repo, cdp

    def test_a_dirty_scan_still_shows_the_model_claim(self):
        repo, cdp = self._model_repo()
        L.dirty(repo, BASE, "\n// wip\n")
        cdp.scan()
        self.assertEqual(live_ids(cdp), ["t.one"])
        self.assertEqual(check_no_silent_loss(cdp), [])
        self.assertTrue(cdp.answering_snapshot()["ephemeral"])
        self.assertEqual([c["id"] for c in cdp.query_json("claims")["claims"] if c["id"].startswith("t.")],
                         ["t.one"])

    def test_a_clean_scan_of_a_new_commit_keeps_the_model_claim(self):
        repo, cdp = self._model_repo()
        L.commit_series(repo, BASE, 1)
        cdp.scan()
        self.assertEqual(live_ids(cdp), ["t.one"])
        self.assertEqual(check_no_silent_loss(cdp), [])

    def test_a_scan_of_a_commit_that_edits_the_anchored_file_reverifies_the_claim(self):
        repo, cdp = self._model_repo()
        L.commit_series(repo, CHILD, 1)
        cdp.scan()
        backend, _ = cdp.open()
        try:
            row = next(c for c in backend.read_artifact("state")["claims"] if c["id"] == "t.one")
        finally:
            backend.close()
        self.assertIsNone(row["claim_reviewed_at"])

    def test_a_scan_that_cannot_carry_says_where_the_claims_are(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        repo.git("checkout", "-q", "-b", "other")
        L.dirty(repo, BASE, "\n// other\n")
        repo.commit("other")
        cdp.scan()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")])
        other_sha = repo.head()
        repo.git("checkout", "-q", "main")
        L.dirty(repo, BASE, "\n// main\n")
        repo.commit("main moves on")
        out = cdp.run("scan").stdout
        self.assertIn("1 model claim(s) exist in snapshot %s" % other_sha[:12], out)
        self.assertEqual(live_ids(cdp), [])
        self.assertEqual(len(snapshots(cdp)), 2)  # and the other branch's snapshot is untouched
        cdp.run("gc")
        self.assertEqual(len(snapshots(cdp)), 2)

    def test_scan_after_scan_is_stable(self):
        repo, cdp = self._model_repo()
        L.dirty(repo, BASE, "\n// wip\n")
        cdp.scan()
        first = cdp.artifacts()
        cdp.scan()
        self.assertEqual(cdp.artifacts()["claims"], first["claims"])

    def test_scan_of_a_repo_without_model_patches_is_unchanged(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.commit_series(repo, BASE, 1)
        cdp.scan()
        backend, _ = cdp.open()
        try:
            self.assertEqual([p["author_kind"] for p in backend.load_patches()], ["python"])
        finally:
            backend.close()


class NonGitChangeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.src = self.tmp / "plain"
        (self.src / "src").mkdir(parents=True)
        (self.src / "src" / "A.java").write_text("package p;\npublic class A { int a() { return 1; } }\n")
        (self.src / "src" / "B.java").write_text("package p;\npublic class B { int b() { return 2; } }\n")
        self.cdp = Cdp(self.tmp, self.src)

    def test_a_changed_plain_directory_is_not_answered_from_the_old_scan(self):
        self.cdp.scan()
        sha1 = self.cdp.answering_snapshot()["commit_sha"]
        (self.src / "src" / "C.java").write_text("package p;\npublic class C { int c() { return 3; } }\n")
        (self.src / "src" / "A.java").write_text("package p;\npublic class A { int a() { return 9; } }\n")
        self.assertIsNone(self.cdp.answering_snapshot(), "an unscanned tree must read as 'scan needed'")
        out = self.cdp.run("query", "stats", check=False)
        self.assertIn("scan", (out.stdout + out.stderr).lower())
        self.cdp.scan()
        self.assertNotEqual(self.cdp.answering_snapshot()["commit_sha"], sha1)
        self.assertIn("C.java", json.dumps(self.cdp.artifacts(["inventory"])["inventory"]))

    def test_an_unchanged_plain_directory_keeps_its_snapshot_and_ignores_excluded_files(self):
        self.cdp.scan()
        sha1 = self.cdp.answering_snapshot()["commit_sha"]
        (self.src / ".cursor").mkdir()
        (self.src / ".cursor" / "rules.md").write_text("x")
        (self.src / "src" / "A.java").touch()
        self.assertEqual(self.cdp.answering_snapshot()["commit_sha"], sha1)

    def test_old_plain_snapshots_do_not_pile_up(self):
        self.cdp.scan()
        for i in range(3):
            (self.src / "src" / "A.java").write_text("package p;\npublic class A { int a() { return %d; } }\n" % (i + 10))
            self.cdp.scan()
        self.assertEqual(len(snapshots(self.cdp)), 1)


@L.needs_git
class ArchiveScopedToSnapshotTest(LayoutCase):
    def test_verify_full_on_a_refreshed_snapshot_ignores_another_snapshots_archive(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        sha_a = repo.head()
        cdp.inject_model_patch("root/svc", [claim("t.one", "com.example.svc.Child")], generation=1, run_id="cdp-aaaaaaaaaaaa")
        repo.commit("empty")
        cdp.refresh()  # B holds a copy of A's gen1
        repo.git("checkout", "-q", sha_a)
        cdp.inject_model_patch("root/svc", [claim("t.two", "com.example.svc.Base", file=BASE, line=3,
                                                    anchor="public abstract class Base {")],
                               generation=2, run_id="cdp-bbbbbbbbbbbb")
        cdp.inject_model_patch("root/svc", [claim("t.three", "com.example.svc.Provisioner",
                                                    file="src/main/java/com/example/svc/Provisioner.java", line=3,
                                                    anchor="public interface Provisioner {")],
                               generation=3, run_id="cdp-cccccccccccc")
        cdp.run("compact", "--compact-threshold", "0")
        cdp.run("verify", "--full")
        repo.git("checkout", "-q", "main")
        proc = cdp.run("verify", "--full", check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(live_ids(cdp), ["t.one"])

    def test_the_old_schema_migrates_and_backfills_unambiguous_archive_rows(self):
        from cdp.store import SqliteStore
        from cdp.store import sqlite_backend as sb
        db = self.tmp / "old" / "index.db"
        db.parent.mkdir()
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        for version, script in enumerate(sb.MIGRATIONS[:10], start=1):
            conn.executescript(script)
            conn.execute("INSERT INTO schema_version VALUES (?)", (version,))
        self.assertNotIn("snapshot_id", [r[1] for r in conn.execute("PRAGMA table_info(claim_patches_archive)")])
        for sid, sha in ((1, "a" * 40), (2, "b" * 40), (3, "c" * 40)):
            conn.execute("INSERT INTO snapshot_meta (id, repo_id, commit_sha, ephemeral, created_at) VALUES (?,?,?,0,'t')",
                         (sid, "r", sha))
        for sid, hashes in ((1, ["h1", "shared"]), (2, ["shared"]), (3, ["h3"])):
            part = {"scopes": [{"node": "n%s" % h, "scope_hash": h} for h in hashes]}
            conn.execute("INSERT INTO snapshot_artifact (snapshot_id, name, payload) VALUES (?, 'partition', ?)",
                         (sid, json.dumps(part)))
        for h in ("h1", "shared", "h3", "orphan"):
            conn.execute("INSERT INTO claim_patches_archive (scope_hash, run_id, payload) VALUES (?, 'r', '{}')", (h,))
        conn.commit()
        conn.close()
        store = SqliteStore(db)
        try:
            rows = dict(store._conn.execute("SELECT scope_hash, snapshot_id FROM claim_patches_archive").fetchall())
        finally:
            store.close()
        self.assertEqual(rows, {"h1": 1, "shared": None, "h3": 3, "orphan": None})
        # a legacy (NULL) row stays visible to a snapshot whose partition names its scope
        store = SqliteStore(db)
        try:
            store.use_snapshot("r", "b" * 40)
            part = store.read_artifact("partition")
            self.assertEqual(len(store.load_patches_full(part)), 1)
        finally:
            store.close()


@L.needs_git
class EmptyRollbackTargetTest(LayoutCase):
    def test_empty_targets_are_clean_errors(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        for flag in ("--to-run", "--to-snapshot"):
            for value in ("", "  "):
                proc = cdp.run("rollback", flag, value, check=False)
                self.assertEqual(proc.returncode, 2 if "usage" in proc.stderr else proc.returncode)
                self.assertNotEqual(proc.returncode, 0)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("empty", (proc.stdout + proc.stderr).lower())
        backend, _ = cdp.open()
        try:
            self.assertEqual(backend.read_artifact("rollback", {"events": []})["events"], [])
        finally:
            backend.close()

    def test_resolve_run_id_rejects_empty(self):
        from cdp import rollback
        from cdp.util import CdpError
        for value in ("", None):
            with self.assertRaises(CdpError):
                rollback.resolve_run_id(value, [])

    def test_mcp_rejects_an_empty_repo(self):
        from mcp_server import tools
        from cdp.util import ArgError
        for value in ("", "   "):
            with self.assertRaises(ArgError):
                tools._paths(value)


if __name__ == "__main__":
    unittest.main()
