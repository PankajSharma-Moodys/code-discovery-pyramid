"""The vendored skill copy is generated, and this proves it.

`.claude/skills/cdp/` is the form CDP ships in — one directory, no install step.
It is also, now that the product lives at the repository root, a *copy*. A copy
that can be hand-edited is a second source of truth, and the drift is silent:
the edit works for whoever made it, because the skill is what their harness
loads, and is invisible to everyone running from the root.

So the copy is asserted byte-identical to its source. Editing the vendored tree
fails this test with the differing paths named; `cdp install --self` is the only
supported way to change it.
"""

from __future__ import annotations

import filecmp
import unittest
from pathlib import Path

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.cli import DIST_MEMBERS, _DIST_IGNORE

VENDORED = SKILL_ROOT / ".claude" / "skills" / "cdp"


def _members(directory: Path) -> set:
    """Names in `directory`, minus anything `install` would not have copied."""
    names = {p.name for p in directory.iterdir()}
    return names - set(_DIST_IGNORE(str(directory), sorted(names)))


def _compare(left: Path, right: Path, rel: str, differing: list, missing: list) -> None:
    """Recursively compare two trees, accumulating differences rather than
    stopping at the first — a drift report naming one file when six drifted
    sends the reader back round the loop five more times."""
    left_names, right_names = _members(left), _members(right)
    for name in sorted(left_names - right_names):
        missing.append("%s%s (absent from vendored copy)" % (rel, name))
    for name in sorted(right_names - left_names):
        missing.append("%s%s (present in vendored copy, not in source)" % (rel, name))
    for name in sorted(left_names & right_names):
        lp, rp = left / name, right / name
        if lp.is_dir() != rp.is_dir():
            differing.append("%s%s (file/directory mismatch)" % (rel, name))
        elif lp.is_dir():
            _compare(lp, rp, "%s%s/" % (rel, name), differing, missing)
        elif not filecmp.cmp(lp, rp, shallow=False):
            differing.append("%s%s" % (rel, name))


class VendoredCopyTest(unittest.TestCase):
    def test_vendored_copy_exists(self) -> None:
        self.assertTrue(
            VENDORED.is_dir(),
            "no vendored skill at %s — run `cdp install --self`" % VENDORED,
        )

    def test_vendored_copy_is_byte_identical(self) -> None:
        if not VENDORED.is_dir():
            self.skipTest("no vendored copy; covered by test_vendored_copy_exists")
        differing: list = []
        missing: list = []
        for member in DIST_MEMBERS:
            src, dst = SKILL_ROOT / member, VENDORED / member
            if not dst.exists():
                missing.append("%s (absent from vendored copy)" % member)
                continue
            if src.is_dir():
                _compare(src, dst, "%s/" % member, differing, missing)
            elif not filecmp.cmp(src, dst, shallow=False):
                differing.append(member)
        if differing or missing:
            self.fail(
                "vendored copy has drifted from the source tree.\n"
                "  differing: %s\n  structural: %s\n"
                "Do not edit .claude/skills/cdp/ by hand; run `cdp install --self`."
                % (differing or "none", missing or "none")
            )

    def test_distribution_excludes_the_repository(self) -> None:
        """The allow-list must not vendor the repo into every target.

        Before the move to the root, `install` was a `copytree` of the whole
        skill directory with an ignore list. At the root that same shape would
        ship `.git/`, `.venv/` and the design documents.
        """
        if not VENDORED.is_dir():
            self.skipTest("no vendored copy")
        self.assertEqual(_members(VENDORED), set(DIST_MEMBERS))
        for forbidden in (".git", ".venv", "PHASE", "RESEARCH_GRAPHIFY.md",
                          "CDP_CLI_SCOPE.md", "ARCHITECTURE.md", "pyproject.toml"):
            self.assertFalse(
                (VENDORED / forbidden).exists(),
                "%s was vendored into the skill copy" % forbidden,
            )


if __name__ == "__main__":
    unittest.main()
