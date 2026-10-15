"""C2/C1: a stale scope is re-reviewed from its changed files and stale claims only."""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import repo_layouts as L
from repo_layouts import Cdp

SVC = "src/main/java/com/example/svc/"
CHILD = SVC + "Child.java"

# A leaf: one claim per Java file listed under "Your scope", anchored on its package line.
STUB = r'''
import json, re, sys
from pathlib import Path
log, prompt, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
text, repo = prompt.read_text(), Path(sys.argv[4])
scope = text.split("## Your scope", 1)[1].split("If you encounter", 1)[0]
files = [f for f in re.findall(r"- `([^`]+)`", scope) if f.endswith(".java")]
claims = []
for f in files:
    lines = (repo / f).read_text().splitlines()
    n = next(i for i, l in enumerate(lines, 1) if l.startswith("package "))
    stem = Path(f).stem
    claims.append({"id": "svc." + stem.lower(), "kind": "naming", "subject": "com.example.svc." + stem,
                   "confidence": "high", "statement": stem + " lives in the svc package.",
                   "evidence": [{"file": f, "line": n, "anchor": lines[n - 1]}]})
with log.open("a") as fh:
    fh.write(json.dumps({"chars": len(text), "files": files, "rereview": "## Re-review" in text}) + chr(10))
run_id = re.search(r"cdp-[0-9a-f]{12}(?:-r[0-9]+)?", text).group(0)  # the run its prompt names, as a real leaf
out.write_text(json.dumps({"schema_version": "1.0.0", "node": out.stem.replace("__", "/"), "run_id": run_id,
                           "status": "complete", "claims": claims, "unknowns": []}))
'''


@L.needs_git
class RereviewTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = L.java_inheritance(self.tmp)
        for i in range(6):  # a scope big enough that its structure outweighs the re-review text
            methods = "".join("    public int m%d() {\n        return %d;\n    }\n" % (k, k) for k in range(25))
            self.repo.write(SVC + "Pad%d.java" % i, "package com.example.svc;\n\npublic class Pad%d {\n%s}\n" % (i, methods))
        self.repo.commit("pad")
        self.cdp = Cdp(self.tmp, self.repo.path)
        self.cdp.scan()
        (self.tmp / "stub.py").write_text(STUB)
        self.log = self.tmp / "log.jsonl"

    def run_leaf(self, *flags):
        cmd = "%s %s %s" % (sys.executable, self.tmp / "stub.py", self.log)
        # the stub takes the repo root as a 4th argument, after the prompt and patch paths
        wrapper = self.tmp / "wrap.py"
        wrapper.write_text("import subprocess, sys\nsys.exit(subprocess.call(%r + sys.argv[1:] + [%r]))\n"
                           % ([sys.executable, str(self.tmp / "stub.py"), str(self.log)], str(self.repo.path)))
        self.cdp.run("run", *(() if "--stale-only" in flags else ("--wave-all",)), *flags, "--runner-cmd", "%s %s" % (sys.executable, wrapper))
        return [json.loads(l) for l in self.log.read_text().splitlines()]

    def leaf_claims(self):
        backend, store = self.cdp.open()
        try:
            return {c["id"]: c for c in store.state["claims"] if c["id"].startswith("svc.")}
        finally:
            backend.close()

    def edit_child(self, i):
        text = self.repo.read(CHILD)
        idx = text.rindex("}")
        self.repo.write(CHILD, text[:idx] + "\n    public int more%d() {\n        return %d;\n    }\n}\n" % (i, i))
        return self.repo.commit("edit child %d" % i)

    def test_changed_file_sends_only_that_file_and_keeps_the_other_claims(self):
        first = self.run_leaf()
        full = first[0]
        self.assertEqual(len(full["files"]), 10)
        before = self.leaf_claims()
        self.assertEqual(len(before), 10)
        sizes = []
        for i in range(3):
            head = self.edit_child(i)
            out = self.cdp.refresh().stdout + self.cdp.run("status").stdout
            rows = self.run_leaf("--resume")
            self.assertEqual(len(rows), 1 + i + 1, "one dispatch per edit, not one per changed scope hash")
            last = rows[-1]
            self.assertEqual(last["files"], [CHILD], "only the changed file reaches the leaf")
            self.assertTrue(last["rereview"])
            sizes.append(last["chars"])
            now = self.leaf_claims()
            self.assertEqual(sorted(now), sorted(before), "no claim lost to the partial review")
            self.assertEqual(now["svc.child"]["claim_reviewed_at"], head, "stale claim re-reviewed")
            for cid in ("svc.base", "svc.provisioner"):
                self.assertEqual(now[cid]["claim_reviewed_at"], before[cid]["claim_reviewed_at"], "kept as is")
        self.assertTrue(all(s < full["chars"] for s in sizes), (sizes, full["chars"]))

    def test_nothing_stale_sends_nothing_and_new_file_is_reviewed_alone(self):
        self.run_leaf()
        self.repo.write("pom.xml", self.repo.read("pom.xml") + "\n<!-- note -->\n")  # cited by no claim
        self.repo.commit("pom note")
        refresh = self.cdp.refresh().stdout
        rows = self.run_leaf("--resume")
        self.assertEqual(len(rows), 1, "the changed scope holds no stale claim: nothing is dispatched")
        self.repo.write(SVC + "Extra.java", "package com.example.svc;\n\npublic class Extra {\n}\n")
        self.repo.commit("add Extra")
        self.cdp.refresh()
        rows = self.run_leaf("--resume")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["files"], [SVC + "Extra.java"])
        self.assertEqual(sorted(self.leaf_claims()), sorted(["svc.base", "svc.child", "svc.childtest", "svc.extra", "svc.provisioner"] + ["svc.pad%d" % i for i in range(6)]))

    def test_stale_only_uses_the_plan_and_second_run_is_clean(self):
        self.run_leaf()
        self.edit_child(0)
        self.cdp.refresh()
        rows = self.run_leaf("--stale-only")
        self.assertEqual(rows[-1]["files"], [CHILD])
        again = self.cdp.run("run", "--stale-only", "--runner-cmd", "false").stdout
        self.assertIn("zero scopes need review", again)

    def test_prompts_and_collect_follow_the_same_plan(self):
        import subprocess
        self.run_leaf()
        head = self.edit_child(0)
        self.cdp.refresh()
        self.cdp.run("prompts")
        prompt = next((self.cdp.home / "work").rglob("prompts/root__svc.md"))
        text = prompt.read_text()
        self.assertIn("## Re-review", text)
        out = re.search(r"Write your patch to `([^`]+)`", text).group(1)
        subprocess.run([sys.executable, str(self.tmp / "stub.py"), str(self.log), str(prompt), out,
                        str(self.repo.path)], check=True)
        self.cdp.run("collect")
        now = self.leaf_claims()
        self.assertEqual(len(now), 10)
        self.assertEqual(now["svc.child"]["claim_reviewed_at"], head)
        self.assertNotEqual(now["svc.base"]["claim_reviewed_at"], head)


if __name__ == "__main__":
    unittest.main()
