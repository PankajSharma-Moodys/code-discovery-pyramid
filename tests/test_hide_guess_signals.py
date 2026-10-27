"""H1: the extractors' internal `guess:` file signals stay in the store and feed settle, but the file
view and the leaf prompt's structure section show only real signals."""

from __future__ import annotations

import copy
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import have_git  # noqa: F401  (sets sys.path)

from cdp import prompts
from cdp.cli import main
from cdp.jtypes import GUESS_PREFIX, settle_extraction
from cdp.query import Store
from cdp.query.lookup import q_file
from cdp.query.render import render

KID = '''package app.x;

import org.springframework.stereotype.Service;

@Service
public class Kid extends Missing {
}
'''


@unittest.skipUnless(have_git(), "needs git")
class HideGuessSignalsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        repo = tmp / "repo"
        (repo / "src/main/java/app/x").mkdir(parents=True)
        (repo / "pom.xml").write_text("<project><groupId>app</groupId><artifactId>x</artifactId>"
                                      "<version>1</version></project>")
        (repo / "src/main/java/app/x/Kid.java").write_text(KID)
        for cmd in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", *cmd], cwd=repo, check=True)
        main(["scan", "--repo", str(repo), "--state-dir", str(tmp / "state"), "--quiet"])
        cls.store = Store(tmp / "state")
        cls.rel = "src/main/java/app/x/Kid.java"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.tmp.cleanup()

    def test_store_keeps_the_guess_mark_next_to_the_real_signal(self) -> None:
        sigs = self.store.extraction["files"][self.rel]["signals"]
        self.assertIn("di:Service", sigs)
        self.assertEqual([s for s in sigs if s.startswith(GUESS_PREFIX)], ["guess:app.x.Missing"])

    def test_file_view_hides_guess_and_keeps_real_signals(self) -> None:
        result = q_file(self.store, self.rel)
        found = result["found"][0]
        self.assertEqual(found["signals"], ["di:Service"])
        text = render(result)
        self.assertIn("signals: di:Service", text)
        self.assertNotIn("guess:", text)

    def test_file_view_with_only_guess_marks_prints_no_signals_line(self) -> None:
        result = q_file(self.store, self.rel)
        result["found"][0]["signals"] = ["guess:a.B"]
        self.assertNotIn("signals:", render(result))

    def test_prompt_structure_hides_guess_and_counts_real_signals(self) -> None:
        ex = copy.deepcopy(self.store.extraction)
        ex["files"]["other/B.java"] = {"signals": ["di:Service", "guess:p.Q", "guess:p.R"]}
        structure = prompts._structure(ex, {self.rel, "other/B.java"})
        self.assertEqual(structure["signals"], {"di:Service": ["other/B.java", self.rel]})
        section = prompts._structure_section(structure)
        self.assertIn("**Signals seen in this scope:** di:Service (2)", section)
        self.assertNotIn("guess:", section)

    def test_settle_still_reads_the_guess_marks(self) -> None:
        ex = self.store.extraction
        before = copy.deepcopy(ex)
        with_marks = settle_extraction(ex)
        self.assertEqual(ex, before)  # input untouched
        stripped = copy.deepcopy(ex)
        for info in stripped["files"].values():
            info["signals"] = prompts.visible_signals(info["signals"])
        # the guess marks drive settle: without them the settled output differs from the scan's
        self.assertNotEqual(settle_extraction(stripped), with_marks)

    def test_visible_signals(self) -> None:
        self.assertEqual(prompts.visible_signals(["a", "guess:x", "b"]), ["a", "b"])
        self.assertEqual(prompts.visible_signals(None), [])


if __name__ == "__main__":
    unittest.main()
