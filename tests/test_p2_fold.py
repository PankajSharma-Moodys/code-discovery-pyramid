"""P2: indexed knowledge is never silently lost (L1-L3, L5, L8, I1, I2, I5, I7) and derived
claims are regenerated on every scan and refresh (C3/L1 family).

Two layers: `fold` on synthetic logs (the rule itself), then the CLI on real temp git repos."""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from helpers import make_repo

import repo_layouts as L
from repo_layouts import Cdp, check_derived_claims_live, check_no_silent_loss, check_refresh_equals_scan
from test_layouts import BASE, CHILD, claim

from cdp import generations
from cdp.rollback import Exclusions
from cdp.state import fold, fold_hash

A = "a/src/main/java/com/example/a/Alpha.java"
B = "b/src/main/java/com/example/b/Beta.java"
ALPHA_ANCHOR = "public class Alpha {"


def _claim(cid, subject, kind="naming", node=None, statement=None):
    row = {"id": cid, "kind": kind, "subject": subject, "confidence": "high",
           "statement": statement or "Statement %s about %s." % (cid, subject),
           "evidence": [{"file": "f.java", "line": 1, "anchor": "x"}]}
    if node:
        row["source_node"] = node
    return row


def _patch(node, claims, generation=1, status="complete", author="llm", run="r", no=None, unknowns=()):
    p = {"node": node, "run_id": run, "status": status, "author_kind": author, "generation": generation,
         "claims": claims, "unknowns": list(unknowns)}
    if no is not None:
        p["patch_no"] = no
    return p


def live_ids(folded):
    return {c["id"] for c in folded["claims"]}


class FoldRuleTest(unittest.TestCase):
    """The new fold on synthetic logs (no repo, so no anchor verification)."""

    xref = {"symbols": {}}

    def fold(self, patches, **kw):
        return fold(patches, self.xref, None, **kw)

    def derived(self):
        return _patch("root", [_claim("d.svc", "svc", node="root/svc"), _claim("d.root", "root")],
                      author="python")

    def test_l1_a_leaf_patch_for_scope_root_leaves_every_derived_claim_live(self):
        # generation 2 outranks the derived patch's generation 1 under the old per-node rule
        folded = self.fold([self.derived(), _patch("root", [_claim("m.root", "other")], generation=2)])
        self.assertEqual(live_ids(folded), {"d.svc", "d.root", "m.root"})

    def test_l2_an_abandoned_or_invalid_attempt_removes_nothing(self):
        failed = {"node": "root/svc", "run_id": "r", "status": "failed", "error": "abandoned after 3 attempts"}
        invalid = {"node": "root/svc", "run_id": "r", "status": "invalid", "error": "bad"}
        folded = self.fold([self.derived(), failed, invalid])
        self.assertEqual(live_ids(folded), {"d.svc", "d.root"})
        self.assertIn("root/svc", {u["source_node"] for u in folded["unknowns"]})  # the gap is still stated

    def test_a_failed_retry_does_not_supersede_an_accepted_generation(self):
        good = _patch("root/svc", [_claim("m.1", "s1")], generation=1)
        failed = {"node": "root/svc", "run_id": "r", "status": "failed", "error": "later attempt died"}
        self.assertEqual(live_ids(self.fold([self.derived(), good, failed])), {"d.svc", "d.root", "m.1"})

    def test_a_scope_keeps_only_its_latest_accepted_generation(self):
        folded = self.fold([_patch("root/svc", [_claim("m.1", "s1")], generation=1),
                            _patch("root/svc", [_claim("m.2", "s2")], generation=2)])
        self.assertEqual(live_ids(folded), {"m.2"})

    def test_l3_answers_on_different_subjects_accumulate(self):
        answers = [_patch("root/svc", [_claim("h.%d" % i, "subject.%d" % i)], generation=i, author="human")
                   for i in range(1, 7)]
        self.assertEqual(live_ids(self.fold(answers)), {"h.%d" % i for i in range(1, 7)})

    def test_l3_a_newer_answer_replaces_an_older_one_only_for_the_same_subject_and_kind(self):
        old = _patch("root/svc", [_claim("h.old", "subject.a", statement="First view of a.")], 1, author="human")
        new = _patch("root/svc", [_claim("h.new", "subject.a", statement="Second view of a.")], 2, author="human")
        other_kind = _patch("root/svc", [_claim("h.kind", "subject.a", kind="entity")], 3, author="human")
        self.assertEqual(live_ids(self.fold([old, new, other_kind])), {"h.new", "h.kind"})

    def test_an_answer_does_not_replace_the_scopes_leaf_claims(self):
        leaf = _patch("root/svc", [_claim("m.leaf", "s1")], generation=1)
        answer = _patch("root/svc", [_claim("h.1", "s2")], generation=2, author="human")
        self.assertEqual(live_ids(self.fold([leaf, answer])), {"m.leaf", "h.1"})

    def test_the_fold_is_order_independent(self):
        log = [self.derived(), _patch("root/svc", [_claim("m.1", "s1")], 1), _patch("root/svc", [_claim("m.2", "s2")], 2),
               _patch("root/svc", [_claim("h.1", "s3")], 3, author="human")]
        self.assertEqual(live_ids(self.fold(log)), live_ids(self.fold(list(reversed(log)))))

    def test_i5_an_exclusion_is_a_range_of_patch_numbers(self):
        patches = [_patch("root/a", [_claim("m.a", "sa")], no=1), _patch("root/b", [_claim("m.b", "sb")], no=2),
                   _patch("root/c", [_claim("m.c", "sc")], no=3)]
        ex = Exclusions([({"r"}, 1, 2)])
        self.assertEqual(live_ids(self.fold(patches, excluded_run_ids=ex)), {"m.c"})  # no 3 came after the rollback

    def test_a_rollback_never_removes_the_scans_own_claims(self):
        derived = dict(self.derived(), patch_no=0)
        folded = self.fold([derived], excluded_run_ids=Exclusions([({"r"}, 0, 5)]))
        self.assertEqual(live_ids(folded), {"d.svc", "d.root"})

    def test_a_legacy_run_only_exclusion_still_works(self):
        self.assertEqual(live_ids(self.fold([_patch("root/a", [_claim("m.a", "sa")])],
                                            excluded_run_ids=frozenset({"r"}))), set())

    def test_compaction_candidates_are_exactly_what_the_fold_no_longer_reads(self):
        log = [self.derived(), _patch("root/svc", [_claim("m.1", "s1")], 1), _patch("root/svc", [_claim("m.2", "s2")], 2),
               _patch("root/svc", [_claim("h.1", "s3")], 3, author="human"),
               _patch("root/svc", [_claim("h.2", "s3", statement="Newer view.")], 4, author="human")]
        out = generations.superseded_indexes(log)
        self.assertEqual(out, [1, 3])  # old leaf generation, old answer for the same subject
        kept = [p for i, p in enumerate(log) if i not in out]
        self.assertEqual(live_ids(self.fold(kept)), live_ids(self.fold(log)))
        self.assertEqual(self.fold(kept)["provenance"]["fold_hash"], self.fold(log)["provenance"]["fold_hash"])

    def test_a_superseded_patch_that_alone_holds_an_unknown_is_not_a_compaction_candidate(self):
        unknown = {"question": "Why is this here?", "why_unresolved": "no doc", "needs": "needs_human"}
        log = [_patch("root/svc", [_claim("m.1", "s1")], 1, unknowns=[unknown]),
               _patch("root/svc", [_claim("m.2", "s2")], 2)]
        self.assertEqual(generations.superseded_indexes(log), [])

    def test_keep_generations_keeps_that_many_hot(self):
        log = [_patch("root/svc", [_claim("m.%d" % g, "s%d" % g)], g) for g in (1, 2, 3)]
        self.assertEqual(generations.superseded_indexes(log, 1), [0, 1])
        self.assertEqual(generations.superseded_indexes(log, 2), [0])

    def test_fold_hash_ignores_the_patch_number_stamp(self):
        plain = [_patch("root/svc", [_claim("m.1", "s1")])]
        numbered = [dict(plain[0], patch_no=7)]
        self.assertEqual(fold(plain, self.xref)["provenance"]["fold_hash"],
                         fold(numbered, self.xref)["provenance"]["fold_hash"])
        self.assertEqual(fold_hash(plain, self.xref, None), fold_hash(plain, self.xref, None))


@L.needs_git
class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def multi(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        return repo, cdp

    def a_claim(self, cid="t.a", subject="com.example.a.Alpha"):
        return claim(cid, subject, file=A, line=3, anchor=ALPHA_ANCHOR)

    def state_claims(self, cdp):
        backend, _ = cdp.open()
        try:
            return backend.read_artifact("state")["claims"]
        finally:
            backend.close()

    def inbox(self, cdp):
        backend, _ = cdp.open()
        try:
            return backend._inbox_dir()
        finally:
            backend.close()


class DerivedClaimsAreRegeneratedTest(RepoCase):
    def test_refresh_regenerates_derived_claims_so_counts_follow_the_tree(self):
        repo = L.new_repo(self.tmp, "svc")
        repo.write("pom.xml", L.pom("svc"))
        for i in range(2):
            repo.write("src/main/java/com/example/svc/T%d.java" % i,
                       "package com.example.svc;\n\npublic class T%d {\n}\n" % i)
        repo.commit("two classes")
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        for i in range(2, 6):  # more files: every "N files ..." style claim changes
            repo.write("src/main/java/com/example/svc/more/T%d.java" % i,
                       "package com.example.svc.more;\n\npublic class T%d {\n}\n" % i)
        repo.commit("four more, in a new package")
        cdp.refresh()
        self.assertEqual(check_refresh_equals_scan(cdp), [])
        self.assertEqual(check_derived_claims_live(cdp), [])

    def test_refresh_keeps_model_claims_beside_the_regenerated_derived_ones(self):
        repo, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim()])
        L.commit_series(repo, B, 1)
        cdp.refresh()
        ids = {c["id"] for c in self.state_claims(cdp)}
        self.assertIn("t.a", ids)
        self.assertEqual(check_derived_claims_live(cdp), [])
        self.assertEqual(check_no_silent_loss(cdp), [])


class RollbackAndCompactTest(RepoCase):
    def rollback(self, cdp, *args, check=True):
        return cdp.run("rollback", *args, check=check)

    def run_id(self, cdp):
        backend, store = cdp.open()
        try:
            return store.manifest["run_id"]
        finally:
            backend.close()

    def test_i5_a_patch_accepted_after_a_rollback_is_live_and_undo_restores_the_old_one(self):
        repo, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim("t.old")])
        self.rollback(cdp, "--to-run", self.run_id(cdp))
        self.assertNotIn("t.old", {c["id"] for c in self.state_claims(cdp)})
        cdp.inject_model_patch("root/b", [claim("t.new", "com.example.b.Beta", file=B, line=3,
                                                anchor="public class Beta {")])
        self.assertIn("t.new", {c["id"] for c in self.state_claims(cdp)})  # same run id, later patch number
        self.assertEqual(cdp.run("fold", "--check").returncode, 0)
        self.rollback(cdp, "--undo")
        live = {c["id"] for c in self.state_claims(cdp)}
        self.assertEqual({"t.old", "t.new"} - live, set())
        self.assertEqual(cdp.run("fold", "--check").returncode, 0)

    def test_i5_undo_with_nothing_to_undo_is_an_error(self):
        _, cdp = self.multi()
        proc = self.rollback(cdp, "--undo", check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no rollback in force to undo", proc.stderr)

    def test_i7_rolled_back_claims_stay_out_after_three_commits(self):
        repo, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim()])
        self.rollback(cdp, "--to-run", self.run_id(cdp))
        for _ in range(3):
            L.commit_series(repo, B, 1)
            cdp.refresh()
            self.assertNotIn("t.a", {c["id"] for c in self.state_claims(cdp)})
        self.assertEqual(cdp.run("fold", "--check").returncode, 0)
        self.assertEqual(check_no_silent_loss(cdp), [])

    def test_i1_compact_never_changes_the_live_set_and_i2_verify_passes_right_after(self):
        repo, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim("t.one")])
        cdp.inject_model_patch("root/a", [self.a_claim("t.two", "com.example.a.Other")])
        before = json.dumps(self.state_claims(cdp), sort_keys=True)
        out = cdp.run("compact", "--compact-threshold", "0").stdout
        self.assertIn("moved 1", out)
        self.assertEqual(json.dumps(self.state_claims(cdp), sort_keys=True), before)
        self.assertEqual(cdp.run("verify").returncode, 0)
        self.assertEqual(cdp.run("verify", "--full").returncode, 0)
        self.assertEqual(cdp.run("fold", "--check").returncode, 0)

    def test_i1_keep_generations_zero_is_refused_and_moves_nothing(self):
        repo, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim("t.one")])
        before = json.dumps(self.state_claims(cdp), sort_keys=True)
        proc = cdp.run("compact", "--keep-generations", "0", "--compact-threshold", "0", check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("at least 1", proc.stderr)
        self.assertEqual(json.dumps(self.state_claims(cdp), sort_keys=True), before)
        self.assertEqual(check_no_silent_loss(cdp), [])

    def test_a_compacted_log_still_folds_to_the_same_state_after_a_refresh(self):
        repo, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim("t.one")])
        cdp.inject_model_patch("root/a", [self.a_claim("t.two", "com.example.a.Other")])
        cdp.run("compact", "--compact-threshold", "0")
        L.commit_series(repo, B, 1)
        cdp.refresh()
        self.assertEqual(cdp.run("verify").returncode, 0)
        self.assertIn("t.two", {c["id"] for c in self.state_claims(cdp)})


class LenientRunsAndInboxTest(RepoCase):
    def drop(self, cdp, repo, node, evidence, claim_id="t.len"):
        inbox = self.inbox(cdp)
        inbox.mkdir(parents=True, exist_ok=True)
        backend, store = cdp.open()
        run_id = store.manifest["run_id"]
        backend.close()
        patch = {"schema_version": "1.0.0", "node": node, "run_id": run_id, "status": "complete", "unknowns": [],
                 "claims": [{"id": claim_id, "kind": "naming", "subject": "com.example.svc.Child",
                             "confidence": "high", "statement": "Child extends Base and is a provisioner.",
                             "evidence": evidence}]}
        (inbox / (node.replace("/", "__") + ".json")).write_text(json.dumps(patch))

    def test_l8_a_lenient_run_passes_fold_check_and_a_strict_fold_keeps_its_claims(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.run("prompts")
        backend, store = cdp.open()
        node = store.partition["scopes"][0]["node"]
        backend.close()
        good = {"file": CHILD, "line": 5, "anchor": "public class Child extends Base implements Provisioner {"}
        bad = {"file": CHILD, "line": 6, "anchor": "this text is nowhere in the file"}
        self.drop(cdp, repo, node, [good, bad])
        out = cdp.run("collect", "--mode", "lenient").stdout
        self.assertIn("accepted  1", out)
        self.assertEqual(cdp.run("fold", "--check").returncode, 0)          # was: FAIL wrote directly to the view
        self.assertIn("t.len", {c["id"] for c in cdp.open()[0].read_artifact("state")["claims"]})
        fold_out = cdp.run("fold").stdout                                    # strict, but the patch is flagged lenient
        self.assertNotIn("dropped", fold_out)
        self.assertIn("t.len", {c["id"] for c in cdp.open()[0].read_artifact("state")["claims"]})
        self.assertEqual(cdp.run("verify").returncode, 0)

    def test_a_collected_claim_survives_a_later_refresh_with_verify_green(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.run("prompts")
        backend, store = cdp.open()
        node = store.partition["scopes"][0]["node"]
        backend.close()
        good = {"file": CHILD, "line": 5, "anchor": "public class Child extends Base implements Provisioner {"}
        self.drop(cdp, repo, node, [good])
        cdp.run("collect")
        L.commit_series(repo, CHILD, 1)  # edits the anchored file
        cdp.refresh()
        self.assertEqual(cdp.run("verify").returncode, 0)
        self.assertEqual(cdp.run("fold", "--check").returncode, 0)
        L.rename(repo, CHILD, "src/main/java/com/example/svc/Kid.java")
        cdp.refresh()
        self.assertEqual(cdp.run("verify").returncode, 0)
        self.assertIn("t.len", {c["id"] for c in cdp.open()[0].read_artifact("state")["claims"]})

    def test_l8_a_strict_collect_demotes_the_same_claim_and_says_so(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.run("prompts")
        backend, store = cdp.open()
        node = store.partition["scopes"][0]["node"]
        backend.close()
        good = {"file": CHILD, "line": 5, "anchor": "public class Child extends Base implements Provisioner {"}
        bad = {"file": CHILD, "line": 6, "anchor": "this text is nowhere in the file"}
        self.drop(cdp, repo, node, [good, bad])
        out = cdp.run("collect").stdout
        self.assertIn("1 demoted claim(s) had at least one good anchor", out)
        self.assertNotIn("t.len", {c["id"] for c in cdp.open()[0].read_artifact("state")["claims"]})

    def test_fold_reports_every_claim_a_fold_drops_and_the_log_still_holds_it(self):
        repo, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim()])
        repo.write(A, repo.read(A).replace("public class Alpha {", "public class Alphas {"))  # uncommitted
        out = cdp.run("fold").stdout
        self.assertIn("dropped   1 claim(s)", out)
        self.assertIn("1 demoted to unknowns", out)
        self.assertNotIn("t.a", {c["id"] for c in self.state_claims(cdp)})
        self.assertEqual(L.model_claim_ids(cdp.open()[0]), ["t.a"])  # the log was never touched
        repo.git("checkout", "--", A)
        cdp.run("fold")
        self.assertIn("t.a", {c["id"] for c in self.state_claims(cdp)})

    def test_l5_an_abandoned_scope_leaves_nothing_in_the_inbox_for_a_later_collect(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        runner = self.tmp / "bad_runner.py"
        runner.write_text(textwrap.dedent('''
            import json, sys
            from pathlib import Path
            patch = Path(sys.argv[2])
            node = patch.stem.replace("__", "/")
            patch.write_text(json.dumps({"schema_version": "1.0.0", "node": node, "run_id": "x", "status": "complete",
                "unknowns": [], "claims": [{"id": "t.fab", "kind": "naming", "subject": "a.B", "confidence": "high",
                "statement": "A statement about a fabricated place.",
                "evidence": [{"file": "Nope.java", "line": 1, "anchor": "not here"}]}]}))
        '''))
        proc = cdp.run("run", "--wave-all", "--max-attempts", "1", "--runner-cmd", "%s %s" % (sys.executable, runner),
                       check=False)
        inbox = self.inbox(cdp)
        self.assertEqual(list(inbox.glob("*.json")), [], proc.stdout)
        self.assertTrue(list((inbox / "rejected").glob("*.json")))
        self.assertIn("accepted  0", cdp.run("collect").stdout)  # was: the leftover was accepted
        status = json.loads(cdp.run("status", "--json").stdout)
        self.assertEqual([n["status"] for w in status["waves"] for n in w["nodes"]], ["failed"])

    def test_l5_a_rejected_collect_patch_moves_to_rejected_and_is_not_retaken(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.run("prompts")
        inbox = self.inbox(cdp)
        (inbox / "garbage.json").write_text("{not json")
        proc = cdp.run("collect", check=False)
        self.assertEqual(proc.returncode, 1)  # nothing accepted
        out = proc.stdout
        self.assertIn("rejected 1", out)
        self.assertFalse((inbox / "garbage.json").exists())
        self.assertTrue((inbox / "rejected" / "garbage.json").exists())
        self.assertIn("rejected 0", cdp.run("collect").stdout)


if __name__ == "__main__":
    unittest.main()
