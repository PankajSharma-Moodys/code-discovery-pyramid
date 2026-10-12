"""P4: the leaf prompt carries annotations as verbatim, cited source facts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import subprocess

from helpers import have_git  # noqa: F401  (sets sys.path)

from cdp import prompts
from cdp.cli import main
from cdp.prompts import build_prompt
from cdp.query import Store

JOB = '''package app.jobs;

import de.spinscale.dropwizard.jobs.annotations.Every;

@Every("1h")
public class Janitor {
    @Override
    public String toString() { return "x"; }

    @Every(jobName = "AutoScaleJob",
           value = "60s")
    public void run(@Named("pool") String pool) {
    }

    @SuppressWarnings("unchecked")
    public void quiet() { }
}
'''


def _make(tmp: Path) -> Path:
    repo = tmp / "jobsrepo"
    (repo / "src/main/java/app/jobs").mkdir(parents=True)
    (repo / "pom.xml").write_text("<project><groupId>app</groupId><artifactId>jobs</artifactId>"
                                  "<version>1</version></project>")
    (repo / "src/main/java/app/jobs/Janitor.java").write_text(JOB)
    for cmd in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True)
    return repo


def _prompt(store, **kw):
    scope = store.partition["scopes"][0]
    return build_prompt(scope, store.inventory, store.extraction, store.xref,
                        store._load("schedule"), [], "run1", **kw)


@unittest.skipUnless(have_git(), "needs git")
class PromptAnnotationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = _make(Path(cls.tmp.name))
        state = Path(cls.tmp.name) / "state"
        main(["scan", "--repo", str(cls.repo), "--state-dir", str(state), "--quiet"])
        cls.store = Store(state)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.tmp.cleanup()

    def test_prompt_has_verbatim_annotation_with_cited_lines(self) -> None:
        text, stats = _prompt(self.store)
        self.assertIn("@Every(", text)
        self.assertRegex(text, r"Janitor#run L10-11: @Every\(.*60s")
        self.assertIn("@Named", text)  # parameter annotation rides with its method
        self.assertLessEqual(stats["tokens_est"], stats["max_prompt_tokens"])
        self.assertIn("verbatim source facts", text)

    def test_noise_annotations_are_dropped_from_the_prompt_only(self) -> None:
        text, _ = _prompt(self.store)
        self.assertNotIn("@Override", text)
        self.assertNotIn("@SuppressWarnings", text)
        stored = [a["name"] for d in self.store.extraction["defines"] for a in d.get("annotations", [])]
        self.assertIn("Override", stored)

    def test_annotation_rows_shrink_with_row_cap_in_the_existing_loop(self) -> None:
        structure = prompts._structure(self.store.extraction, set(self.store.partition["scopes"][0]["files"]))
        base = structure["annotated"][0]
        structure["annotated"] = [dict(base, fqn="app.C%02d" % i, kind="class") for i in range(30)]
        full = prompts._structure_section(structure, row_cap=120)
        capped = prompts._structure_section(structure, row_cap=20)  # annotation cap = row_cap // 2, floor 10
        self.assertNotIn("more", full.split("### Annotations")[1].split("###")[0])
        self.assertIn("and 20 more", capped.split("### Annotations")[1])
        self.assertLess(len(capped), len(full))
        # shrink order preserved: a tiny budget still tightens inherited -> structure, never errors
        _, stats = _prompt(self.store, max_prompt_tokens=1)
        self.assertTrue(stats["prompt_budget_exhausted"])
        self.assertEqual(stats["prompt_tightened"][-1], "structure(10)")


if __name__ == "__main__":
    unittest.main()
