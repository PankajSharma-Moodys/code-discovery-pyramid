"""P2 link work: verdicts survive a re-scan (M1), a bad patch costs only its own task (M2),
link ids do not move with a commit (M8), and concurrent runs keep every verdict (M9)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from helpers import SKILL_ROOT

from cdp.link import build_tasks, refresh_links, scan_links, unresolved_tasks
from cdp.linkid import link_id
from cdp.store.sqlite_backend import SqliteStore

RUN_PY = SKILL_ROOT / "run.py"
N = 7

RUNNER = textwrap.dedent('''
    import json, re, sys, time
    from pathlib import Path
    mode, prompt, patch = sys.argv[1], Path(sys.argv[2]).read_text(), Path(sys.argv[3])
    time.sleep(0.05)
    task_id = re.search(r"# Link task (\\S+)", prompt).group(1)
    ids = re.findall(r"## candidate (\\S+)", prompt)
    anchor = re.search(r"caller  \\[[^\\]]*\\] \\S+ \\S+ (\\S+):(\\d+)", prompt)
    if mode == "crash" or (mode.startswith("bad:") and mode[4:] in prompt):
        patch.write_text("[1]")  # a malformed patch: a list, not an object
        sys.exit(0)
    patch.write_text(json.dumps({"task_id": task_id, "resolutions": [
        {"link_id": i, "verdict": "match", "reason": "same endpoint",
         "anchor": {"file": anchor.group(1), "line": int(anchor.group(2))}} for i in ids]}))
''')


def edge(source, target, channel, file, line=1, module="m"):
    return {"source": source, "target": target, "channel": channel, "module": module,
            "anchor": {"file": file, "line": line}, "confidence": "high"}


def snapshots(head_a="aaa", head_b="bbb", shift=0):
    caller = [edge("C#call%d" % i, "http:https://x/w%d/:id" % i, "http_out", "A%d.java" % i, 10 + shift)
              for i in range(N)]
    callee = [edge("H#get%d" % i, "route:GET /w%d/{id}" % i, "http_in", "H%d.java" % i, 20 + shift)
              for i in range(N)]
    return [{"repo": "billing", "head": head_a, "dataflow": {"edges": caller}},
            {"repo": "svc", "head": head_b, "dataflow": {"edges": callee}}]


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.elsewhere = self.tmp / "elsewhere"
        self.elsewhere.mkdir()
        self.db = self.tmp / "store" / "index.db"
        self.runner = self.tmp / "runner.py"
        self.runner.write_text(RUNNER)
        store = SqliteStore(self.db)
        store.write_link_edges(scan_links(snapshots()))
        store.close()

    def link(self, *args, mode="good", check=False):
        cmd = [sys.executable, str(RUN_PY), "--state-dir", str(self.home), "link", *args, "--db", str(self.db)]
        if args[0] == "run":
            cmd += ["--runner-cmd", "%s %s %s" % (sys.executable, self.runner, mode)]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.elsewhere),
                              env=dict(os.environ, CDP_HOME=str(self.home)))

    def edges(self):
        store = SqliteStore(self.db)
        try:
            return store.read_link_edges()
        finally:
            store.close()

    def resolved(self):
        return sum(1 for e in self.edges() if e["kind"] == "link" and e["data"].get("resolution"))


class LinkIdTest(unittest.TestCase):
    def test_m8_an_id_ignores_the_commit_and_the_line(self):
        one = scan_links(snapshots("aaa", "bbb", shift=0))["links"][0]
        two = scan_links(snapshots("ccc", "ddd", shift=40))["links"][0]
        self.assertNotEqual(one["caller"]["head"], two["caller"]["head"])
        self.assertEqual(link_id(one), link_id(two))

    def test_m8_an_id_still_tells_two_pairings_apart(self):
        links = scan_links(snapshots())["links"]
        self.assertEqual(len({link_id(l) for l in links}), N)

    def test_m8_an_unrelated_commit_does_not_duplicate_links_on_refresh(self):
        report = scan_links(snapshots("aaa", "bbb"))
        for commit in range(3):  # three commits to one of the two repos, lines moving
            report = refresh_links(report, snapshots("c%d" % commit, "bbb", shift=commit)[:1])
        self.assertEqual(report["totals"]["links"], N)
        self.assertEqual(report["totals"]["decayed"], 0)


class ResolutionsSurviveTest(Case):
    def test_m1_a_rescan_keeps_every_resolution(self):
        self.assertEqual(self.link("run").returncode, 0)
        self.assertEqual(self.resolved(), N)
        store = SqliteStore(self.db)
        store.write_link_edges(scan_links(snapshots("new", "heads")))  # what `link scan` ends with
        store.close()
        self.assertEqual(self.resolved(), N)

    def test_m1_a_resolution_embedded_by_an_older_store_is_kept_through_the_next_scan(self):
        report = scan_links(snapshots())
        report["links"][0]["resolution"] = {"verdict": "match", "reason": "old", "anchor": {"file": "A0.java", "line": 10}}
        store = SqliteStore(self.db)
        store.write_link_edges(report)
        store.write_link_edges(scan_links(snapshots()))
        store.close()
        self.assertEqual(self.resolved(), 1)

    def test_a_resolution_follows_its_link_across_a_commit(self):
        self.link("run")
        store = SqliteStore(self.db)
        store.write_link_edges(scan_links(snapshots("n1", "n2", shift=9)))  # same links, new commits and lines
        store.close()
        self.assertEqual(self.resolved(), N)
        self.assertEqual(unresolved_tasks({"links": [e["data"] for e in self.edges() if e["kind"] == "link"]}), [])


class BadPatchTest(Case):
    def test_m2_a_good_and_a_bad_run_keeps_the_good_resolutions_exits_nonzero_and_the_next_run_finishes(self):
        first = build_tasks(scan_links(snapshots()))[0]["target"]
        proc = self.link("run", mode="bad:" + first)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertEqual(self.resolved(), N - 1)
        self.assertIn("1 of %d task(s) did not complete" % N, proc.stdout)
        again = self.link("run")  # the failed task's lease was released: it is picked up
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("1 task(s)", again.stdout)
        self.assertEqual(self.resolved(), N)

    def test_m2_a_run_where_every_task_fails_exits_1_and_loses_nothing(self):
        proc = self.link("run", mode="crash")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.resolved(), 0)
        self.assertEqual(len([e for e in self.edges() if e["kind"] == "link"]), N)

    def test_m2_a_malformed_patch_does_not_raise_and_releases_its_lease(self):
        from cdp.link import dispatch_link_task
        from test_supervisor import ScriptedRunner, _write

        store = SqliteStore(self.db)
        task = build_tasks(scan_links(snapshots()))[0]
        prompts = self.tmp / "prompts"
        prompts.mkdir()
        for body in ([1], {"task_id": task["task_id"], "resolutions": [1]},
                     {"task_id": task["task_id"], "resolutions": [{"link_id": task["candidates"][0]["link_id"],
                                                                     "verdict": "match", "reason": "x", "anchor": 5}]}):
            row = dispatch_link_task(task, "run-bad", ScriptedRunner([_write(body)]), store, prompts, max_attempts=1)
            self.assertEqual(row["state"], "abandoned", body)
            self.assertTrue(store.acquire_link_lease("run-bad", task["task_id"], 60))
            store.release_link_lease("run-bad", task["task_id"])
        store.close()

    def test_the_failed_patch_is_moved_out_of_the_inbox(self):
        self.link("run", mode="crash")
        inbox = self.home / "work"
        leftovers = [p for p in self.tmp.rglob("*.json") if p.parent.name == "inbox"]
        self.assertEqual(leftovers, [])
        self.assertIsNotNone(inbox)


class ConcurrentRunsTest(Case):
    def test_m9_concurrent_runs_keep_every_resolution(self):
        procs = [subprocess.Popen(
            [sys.executable, str(RUN_PY), "--state-dir", str(self.tmp / ("h%d" % i)), "link", "run", "--db", str(self.db),
             "--runner-cmd", "%s %s good" % (sys.executable, self.runner)],
            cwd=str(self.elsewhere), env=dict(os.environ, CDP_HOME=str(self.tmp / ("h%d" % i))),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(4)]
        outs = [p.communicate(timeout=120) for p in procs]
        self.assertEqual([p.returncode for p in procs], [0, 0, 0, 0], outs)
        self.assertEqual(self.resolved(), N)

    def test_m9_the_lock_is_the_stores_not_the_machine_homes(self):
        self.link("run")
        self.assertTrue(list((self.db.parent / "locks").glob("*.lock")))
        self.assertFalse((self.home / "locks").exists() and list((self.home / "locks").glob("*.lock")))


if __name__ == "__main__":
    unittest.main()


class LinkExitCodesTest(Case):
    def test_m3_collect_exits_1_when_every_patch_is_rejected_and_survives_a_non_object(self):
        out = self.tmp / "tasks-out"
        self.assertEqual(self.link("prompts", "--out", str(out)).returncode, 0)
        (out / "inbox" / "one.json").write_text("[1]")
        (out / "inbox" / "two.json").write_text('{"task_id": "nope"}')
        proc = self.link("collect", "--in", str(out))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("rejected 2", proc.stdout)

    def test_m3_prompts_with_an_always_failing_runner_exits_1(self):
        out = self.tmp / "tasks-out"
        proc = subprocess.run(
            [sys.executable, str(RUN_PY), "--state-dir", str(self.home), "link", "prompts", "--db", str(self.db),
             "--out", str(out), "--runner-cmd", "%s -c 'import sys; sys.exit(3)'" % sys.executable],
            capture_output=True, text=True, cwd=str(self.elsewhere), env=dict(os.environ, CDP_HOME=str(self.home)))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
